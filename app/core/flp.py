"""Lecture d'un projet FL Studio (.flp) : où sont posés les sons (sound kills) dans la playlist.

Format FLP : en-tête « FLhd » (format, nb de canaux, PPQ) puis « FLdt » = suite d'événements.
  id 0-63 : 1 octet | 64-127 : 2 octets | 128-191 : 4 octets | 192-255 : longueur (varint) + données
Événements utiles :
  64  (WORD)  nouveau canal (son index)
  66  (WORD)  tempo (anciennes versions)
  156 (DWORD) tempo x 1000
  196 (TEXT)  fichier du sample du canal
  203 (TEXT)  nom du canal
  233 (DATA)  éléments de la playlist (32 ou 60 octets chacun)
"""
import struct
from pathlib import Path

PATTERN_BASE = 20480


def _text(raw):
    if len(raw) >= 2 and raw[1:2] == b"\x00":
        s = raw.decode("utf-16-le", "ignore")
    else:
        s = raw.decode("latin-1", "ignore")
    return s.split("\x00")[0].strip()


def _events(data):
    i, n = 0, len(data)
    while i < n:
        eid = data[i]
        i += 1
        if eid < 64:
            yield eid, data[i]
            i += 1
        elif eid < 128:
            yield eid, struct.unpack_from("<H", data, i)[0]
            i += 2
        elif eid < 192:
            yield eid, struct.unpack_from("<I", data, i)[0]
            i += 4
        else:
            size, shift = 0, 0
            while True:
                b = data[i]
                i += 1
                size |= (b & 0x7F) << shift
                shift += 7
                if not b & 0x80:
                    break
            yield eid, data[i:i + size]
            i += size


def _items(raw):
    """Éléments de la playlist : (position en ticks, index, longueur en ticks, piste, muet)."""
    for size in (60, 32, 28):
        if len(raw) % size:
            continue
        out, ok = [], True
        for k in range(0, len(raw), size):
            pos, base, idx, length, track = struct.unpack_from("<IHHIH", raw, k)
            if base != PATTERN_BASE:
                ok = False
                break
            flags = struct.unpack_from("<H", raw, k + 18)[0] if size >= 20 else 0
            out.append((pos, idx, length, 500 - track, bool(flags & 0x2000)))
        if ok:
            return out
    return []


def read(path):
    """-> {"ppq", "tempo", "hits": [{"t", "fin", "canal", "sample", "nom", "piste"}]}
    Un « hit » = un son audio posé dans la playlist (les patterns de notes sont ignorés)."""
    raw = Path(path).read_bytes()
    if raw[:4] != b"FLhd":
        raise ValueError("Ce fichier n'est pas un projet FL Studio (.flp).")
    hlen = struct.unpack_from("<I", raw, 4)[0]
    _fmt, _nch, ppq = struct.unpack_from("<hHH", raw, 8)
    p = 8 + hlen
    if raw[p:p + 4] != b"FLdt":
        raise ValueError("Projet FL Studio illisible (pas de données).")
    dlen = struct.unpack_from("<I", raw, p + 4)[0]
    data = raw[p + 8: p + 8 + dlen]

    tempo, channels, cur = 140.0, {}, None
    playlists = []
    for eid, val in _events(data):
        if eid == 156 and isinstance(val, int) and val:
            tempo = val / 1000.0
        elif eid == 66 and isinstance(val, int) and val and tempo == 140.0:
            tempo = float(val)
        elif eid == 64:
            cur = val
            channels.setdefault(cur, {"sample": "", "nom": ""})
        elif eid == 196 and cur is not None:
            channels[cur]["sample"] = _text(val)
        elif eid == 203 and cur is not None:
            channels[cur]["nom"] = _text(val)
        elif eid == 233:
            playlists.append(val)
    if not playlists:
        raise ValueError("Aucune playlist trouvée dans ce projet.")
    items = []
    for pl in playlists:                       # 1re arrangement qui contient quelque chose
        items = _items(pl)
        if items:
            break
    ppq = ppq or 96
    sec = 60.0 / (tempo * ppq)
    hits = []
    for pos, idx, length, track, muted in items:
        if idx >= PATTERN_BASE or muted or idx not in channels:
            continue                           # pattern (notes) ou canal inconnu
        ch = channels[idx]
        if not ch["sample"]:
            continue
        hits.append({"t": round(pos * sec, 4), "fin": round((pos + length) * sec, 4), "canal": idx,
                     "sample": ch["sample"], "nom": ch["nom"] or Path(ch["sample"].replace("\\", "/")).stem,
                     "piste": track})
    hits.sort(key=lambda h: h["t"])
    return {"ppq": ppq, "tempo": tempo, "hits": hits}


def soundkills(path, music=None):
    """Les sound kills du projet : on enlève la musique (le son le plus long ou le même fichier que
    la musique) et on cale le temps 0 sur le début de la musique."""
    info = read(path)
    hits = info["hits"]
    if not hits:
        return info, []
    music_name = Path(music).stem.lower() if music else None

    def is_music(h):
        name = Path(h["sample"].replace("\\", "/")).stem.lower()
        return (music_name and name == music_name) or h["fin"] - h["t"] > 12
    musics = [h for h in hits if is_music(h)]
    offset = min(h["t"] for h in musics) if musics else 0.0
    sk = [dict(h, t=round(h["t"] - offset, 4), fin=round(h["fin"] - offset, 4))
          for h in hits if not is_music(h) and h["t"] >= offset]
    return info, sk

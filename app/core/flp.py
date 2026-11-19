"""Lecture d'un projet FL Studio (.flp) : quels sons sont posés dans la playlist, et quand.

Format FLP : en-tête « FLhd » (PPQ = tics par temps) puis « FLdt » = une suite d'événements.
id < 64 : 1 octet, < 128 : 2 octets, < 192 : 4 octets, sinon : longueur variable + données.
"""
import struct
from dataclasses import dataclass, field
from pathlib import Path

EV_CH_NEW = 64          # nouveau canal (n°)
EV_PAT_NEW = 65
EV_TEMPO_OLD = 66       # tempo entier (vieux FL)
EV_TEMPO = 156          # tempo x 1000
EV_NAME = 192           # nom du canal (vieux FL)
EV_SAMPLE = 196         # chemin du sample du canal
EV_VERSION = 199
EV_PLUGIN_NAME = 203    # nom affiché du canal
EV_PLAYLIST = 233       # éléments de la playlist
EV_ARR_NEW = 99


@dataclass
class Clip:
    time: float           # secondes depuis le début du projet
    channel: int
    name: str
    sample: str
    track: int
    offset: float = 0.0   # début coupé du clip (s)


@dataclass
class FlpProject:
    tempo: float
    ppq: int
    version: str
    clips: list = field(default_factory=list)
    channels: dict = field(default_factory=dict)   # n° -> (nom, sample)


def _text(data, unicode_):
    if unicode_:
        s = data.decode("utf-16-le", errors="ignore")
    else:
        s = data.decode("latin-1", errors="ignore")
    return s.split("\x00")[0].strip()


def _events(buf):
    i, n = 0, len(buf)
    while i < n:
        eid = buf[i]
        i += 1
        if eid < 64:
            yield eid, buf[i]; i += 1
        elif eid < 128:
            yield eid, struct.unpack_from("<H", buf, i)[0]; i += 2
        elif eid < 192:
            yield eid, struct.unpack_from("<I", buf, i)[0]; i += 4
        else:
            size, shift = 0, 0
            while True:
                b = buf[i]; i += 1
                size |= (b & 0x7F) << shift
                shift += 7
                if not b & 0x80:
                    break
            yield eid, buf[i:i + size]; i += size


def read(path):
    raw = Path(path).read_bytes()
    if raw[:4] != b"FLhd":
        raise ValueError("Ce fichier n'est pas un projet FL Studio (.flp).")
    hlen = struct.unpack_from("<I", raw, 4)[0]
    ppq = struct.unpack_from("<H", raw, 8 + 4)[0] or 96
    j = 8 + hlen
    if raw[j:j + 4] != b"FLdt":
        raise ValueError("Projet FL Studio illisible.")
    body = raw[j + 8:j + 8 + struct.unpack_from("<I", raw, j + 4)[0]]

    tempo, version, unicode_ = 140.0, "", True
    channels, cur = {}, None
    playlists = []
    for eid, val in _events(body):
        if eid == EV_VERSION:
            version = val.decode("ascii", errors="ignore").strip("\x00")
            try:
                unicode_ = int(version.split(".")[0]) >= 12
            except ValueError:
                pass
        elif eid == EV_TEMPO:
            tempo = val / 1000.0
        elif eid == EV_TEMPO_OLD and tempo == 140.0:
            tempo = float(val)
        elif eid == EV_CH_NEW:
            cur = val
            channels.setdefault(cur, ["", ""])
        elif eid == EV_PAT_NEW:
            cur = None                      # les noms suivants sont ceux des patterns
        elif eid in (EV_PLUGIN_NAME, EV_NAME) and cur is not None and isinstance(val, (bytes, bytearray)):
            name = _text(val, unicode_)
            if name and not channels[cur][0]:
                channels[cur][0] = name
        elif eid == EV_SAMPLE and cur is not None:
            channels[cur][1] = _text(val, unicode_)
        elif eid == EV_PLAYLIST:
            playlists.append(bytes(val))

    major = int(version.split(".")[0]) if version[:2].isdigit() else 20
    sec_per_tick = 60.0 / (tempo * ppq)
    proj = FlpProject(tempo, ppq, version, channels={k: tuple(v) for k, v in channels.items()})
    for data in playlists[:1]:              # première arrangement = la playlist principale
        size = 60 if (major >= 21 and len(data) % 60 == 0) else 32
        if len(data) % size:
            size = 32 if len(data) % 32 == 0 else 60
        for k in range(0, len(data) - size + 1, size):
            pos, base, idx = struct.unpack_from("<IHH", data, k)
            track = 499 - struct.unpack_from("<H", data, k + 12)[0]
            start_off = struct.unpack_from("<f", data, k + 24)[0]
            if idx >= base and base:        # pattern, pas un son
                continue
            name, sample = proj.channels.get(idx, ("", ""))
            if not name:
                name = Path(sample.replace("\\", "/")).stem if sample else f"Canal {idx}"
            off = start_off * sec_per_tick if 0 < start_off < 1e7 else 0.0
            proj.clips.append(Clip(pos * sec_per_tick, idx, name, sample, track, off))
    proj.clips.sort(key=lambda c: c.time)
    return proj

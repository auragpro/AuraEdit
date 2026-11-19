"""Repères de la musique : à quels moments il y aura un clip, un dash ou un kunai.

Trois sources :
  - les sound kills déjà placés dans l'onglet Sons IA ;
  - un audio avec des sound kills déjà faits (la musique + les sons) : on les retrouve ;
  - un audio de claps : un clap = un repère ; 3 claps différents = clip / dash / kunai.
Et dans l'autre sens : à partir des repères, le logiciel fabrique l'audio de claps.
"""
from pathlib import Path

import numpy as np

from . import audio

SR = 44100
TYPES = ("clip", "dash", "kunai")
LABELS = {"clip": "Clip (kill)", "dash": "Dash", "kunai": "Kunai"}
COLORS = {"clip": "#ff4655", "dash": "#3b9eff", "kunai": "#3ddc97"}


def type_of(name):
    """Type d'un son d'après sa catégorie / son nom (« dash », « kunai », sinon clip)."""
    low = (name or "").lower()
    if "dash" in low:
        return "dash"
    if "kunai" in low or "knife" in low or "blade" in low:
        return "kunai"
    return "clip"


def clean(markers, min_gap=0.06):
    """Trie et retire les doublons trop proches."""
    out = []
    for m in sorted(markers, key=lambda m: m["t"]):
        if out and m["t"] - out[-1]["t"] < min_gap:
            continue
        out.append({"t": round(float(m["t"]), 3), "type": m["type"] if m["type"] in TYPES else "clip"})
    return out


# -------------------------------------------------------------- claps ----

def _band_noise(n, lo, hi, rng):
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, n)
    return x / (np.abs(x).max() + 1e-9)


def _custom_file():
    from .project import config_dir
    return config_dir() / "claps.json"


def custom_claps():
    """{type: chemin} des claps choisis par l'utilisateur (ses propres fichiers audio)."""
    import json
    try:
        d = json.loads(_custom_file().read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if k in TYPES and isinstance(v, str) and Path(v).is_file()}
    except (OSError, ValueError, AttributeError):
        return {}


def set_custom_clap(kind, path):
    """path=None : revenir au clap du logiciel."""
    import json
    d = custom_claps()
    if path:
        d[kind] = str(path)
    else:
        d.pop(kind, None)
    try:
        _custom_file().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    _CACHE.pop(kind, None)


_CACHE = {}


def clap(kind):
    """Le clap de ce type : ton fichier s'il y en a un, sinon celui du logiciel."""
    path = custom_claps().get(kind)
    if path:
        key = (path, Path(path).stat().st_mtime)
        if kind in _CACHE and _CACHE[kind][0] == key:
            return _CACHE[kind][1]
        try:
            y = audio.load(path, SR, 1)[: int(1.5 * SR)]      # 1,5 s max
            nz = np.nonzero(np.abs(y) > 0.02 * (np.abs(y).max() + 1e-9))[0]
            if len(nz):
                y = y[nz[0]:]                                 # on retire le silence du début
                y = (0.9 * y / (np.abs(y).max() + 1e-9)).astype(np.float32)
                _CACHE[kind] = (key, y)
                return y
        except Exception:
            pass
    return builtin_clap(kind)


def builtin_clap(kind):
    """Les 3 claps du logiciel, bien différents pour qu'il les reconnaisse."""
    rng = np.random.default_rng({"clip": 1, "dash": 2, "kunai": 3}[kind])
    n = int(0.18 * SR)
    t = np.arange(n) / SR
    if kind == "clip":                       # clap classique (médium)
        x = _band_noise(n, 900, 3500, rng)
        env = np.zeros(n)
        for d in (0.0, 0.011, 0.022):         # 3 petites claques rapprochées
            k = int(d * SR)
            env[k:] += np.exp(-(t[: n - k]) / (0.006 if d < 0.02 else 0.05))
        y = x * env
    elif kind == "dash":                     # clap grave et sourd
        x = _band_noise(n, 150, 700, rng)
        y = x * np.exp(-t / 0.06) + 0.6 * np.sin(2 * np.pi * 160 * t) * np.exp(-t / 0.05)
    else:                                    # kunai : petit clic très aigu
        x = _band_noise(n, 5000, 12000, rng)
        y = x * np.exp(-t / 0.02) + 0.5 * np.sin(2 * np.pi * 4200 * t) * np.exp(-t / 0.03)
    return (0.9 * y / (np.abs(y).max() + 1e-9)).astype(np.float32)


def export_claps(folder):
    """Écrit les 3 claps en WAV (pour faire soi-même un audio de claps dans FL Studio)."""
    out = []
    for k in TYPES:
        p = Path(folder) / f"clap_{k}.wav"
        audio.save_wav(p, clap(k), SR)
        out.append(str(p))
    return out


def clap_track(markers, duration, music=None, music_gain=0.35):
    """Audio de claps calé sur la musique (et une version avec la musique en fond)."""
    n = int(max(duration, (max((m["t"] for m in markers), default=0) + 1)) * SR)
    y = np.zeros(n, np.float32)
    sounds = {k: clap(k) for k in TYPES}
    for m in markers:
        s = sounds[m["type"]]
        i = int(m["t"] * SR)
        j = min(n, i + len(s))
        if i < n:
            y[i:j] += s[: j - i]
    claps = np.clip(y, -1, 1)
    mixed = None
    if music is not None:
        mus = audio.load(music, SR, 1)[:n]
        mixed = claps.copy()
        mixed[: len(mus)] += music_gain * mus
        mixed = np.clip(mixed, -1, 1)
    return claps, mixed


def _profile(seg):
    """Empreinte d'un son : énergie dans 24 bandes (100 Hz -> 14 kHz)."""
    seg = seg * np.hanning(len(seg))
    mag = np.abs(np.fft.rfft(seg, 4096)) ** 2
    f = np.fft.rfftfreq(4096, 1 / SR)
    edges = np.geomspace(100, 14000, 25)
    p = np.array([mag[(f >= a) & (f < b)].sum() for a, b in zip(edges[:-1], edges[1:])])
    p = np.log1p(p / (p.max() + 1e-12) * 1000)
    return p / (np.linalg.norm(p) + 1e-9)


def _onsets(y, hop=220, min_gap=0.06):
    """Débuts des sons (claps) : montée brusque d'énergie."""
    n = len(y) // hop
    e = np.sqrt((y[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9
    db = 20 * np.log10(e)
    rise = np.zeros(n)
    rise[3:] = db[3:] - db[:-3]                 # montée sur ~15 ms
    floor = np.percentile(db, 20)
    peak = np.percentile(db, 99.5)
    level = floor + 0.35 * (peak - floor)
    out, last = [], -1e9
    for i in range(1, n):
        if db[i] > level and rise[i] > 6 and (i - last) * hop / SR > min_gap:
            out.append(i * hop)
            last = i
    return out


def from_claps(path):
    """Lit un audio de claps et renvoie les repères (le type d'après le clap)."""
    y = audio.load(path, SR, 1)
    if len(y) < SR // 10:
        raise ValueError("Audio de claps vide ou trop court.")
    refs = {k: _profile(clap(k)[: int(0.08 * SR)]) for k in TYPES}
    f = np.fft.rfftfreq(4096, 1 / SR)
    found = []
    for i in _onsets(y):
        seg = y[i: i + int(0.08 * SR)]
        if len(seg) < 256:
            continue
        p = _profile(seg)
        sims = {k: float(p @ r) for k, r in refs.items()}
        best = max(sims, key=sims.get)
        mag = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 4096))
        centroid = float((f * mag).sum() / (mag.sum() + 1e-9))
        found.append((i / SR, best, sims[best], centroid))
    if not found:
        raise ValueError("Aucun clap trouvé dans cet audio.")
    # claps inconnus (ni ceux du logiciel, ni les tiens) : on classe par hauteur grave / médium / aigu
    if np.mean([s for _, _, s, _ in found]) < 0.75:
        cents = np.array([c for *_, c in found])
        lo, hi = np.percentile(cents, 33), np.percentile(cents, 67)
        if hi - lo < 300:                     # un seul type de clap : tout en clips
            return clean([{"t": t, "type": "clip"} for t, *_ in found])
        return clean([{"t": t, "type": "dash" if c < lo else "kunai" if c > hi else "clip"}
                      for t, _, _, c in found])
    return clean([{"t": t, "type": k} for t, k, _, _ in found])


# ------------------------------------------------------- sound kills ----

def from_placements(placements):
    """Repères à partir des sound kills de l'onglet Sons IA."""
    out = []
    for p in placements or []:
        if isinstance(p, dict) and "t" in p:
            out.append({"t": p["t"], "type": type_of(f'{p.get("category", "")} {p.get("sound", "")}')})
    return clean(out)


def from_soundkill_audio(edit_path, music_path, library=None, progress=None):
    """Retrouve les sound kills dans un audio « musique + sons déjà faits »."""
    from . import edit_learning as el
    if library:
        try:
            ex = el.listen(edit_path, music_path, library, progress)
            if ex.detections:
                return clean([{"t": d.t, "type": type_of(f"{d.category} {d.sound}")} for d in ex.detections])
        except ValueError:
            raise
        except Exception:
            pass
    # sans bibliothèque de sons : ce qui « dépasse » de la musique = un sound kill
    from . import music_analysis as ma
    if progress:
        progress("Recherche des sound kills...", 0.3)
    edit = audio.load(edit_path, ma.SR, 1)
    music = audio.load(music_path, ma.SR, 1)
    shift = el.find_shift(edit, music)
    m_al = el._aligned(music, shift, len(edit))
    e, _ = ma.band_spectrogram(edit)
    m, _ = ma.band_spectrogram(m_al)
    n = min(len(e), len(m))
    diff = np.clip(e[:n] - m[:n], 0, None)[:, 8:]            # au-dessus de ~150 Hz
    flux = np.clip(np.diff(diff.sum(1), prepend=0), 0, None)
    thr = np.percentile(flux, 99) * 0.5
    out, last = [], -1e9
    for i in np.nonzero(flux > thr)[0]:
        t = i * ma.DT - shift / ma.SR
        if t - last > 0.12 and t >= 0:
            out.append({"t": t, "type": "clip"})
            last = t
    if progress:
        progress("Terminé", 1.0)
    return clean(out)


def envelope(path, points=1600):
    """Forme de la musique pour l'affichage (volume par tranche)."""
    y = audio.load(path, 11025, 1)
    if not len(y):
        return np.zeros(points), 0.0
    k = max(1, len(y) // points)
    m = len(y) // k
    env = np.abs(y[: m * k]).reshape(m, k).max(1)
    return env / (env.max() + 1e-9), len(y) / 11025

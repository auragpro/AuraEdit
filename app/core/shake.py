"""Shakes « Hit Impulse » posés sur chaque coupe de l'edit : le PEAK (moment le plus fort) tombe
pile sur la coupe entre 2 clips. Durée normale : 4 images avant le peak, 20 après (à 60 i/s).

Recréé à partir du preset Hit Impulse (pack Simple) : léger zoom (bords en miroir), tremblement de
position et de rotation, décalage de couleurs, plus forts de 1x à 5x. IN = punch en zoom avant,
OUT = punch en zoom arrière. Les 9 crans de durée étirent ou resserrent le shake autour du peak.
"""
import math
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import audio

FPS_REF = 60.0           # durées comptées en images de l'edit (60 i/s)
# niveau : (zoom au peak, amplitude position px, décalage chromatique px)
LEVELS = {1: (0.97, 25, 5), 2: (0.95, 30, 6), 3: (0.90, 35, 7), 4: (0.85, 45, 8), 5: (0.80, 60, 9)}
ROT_AMP = 4.5            # degrés
POS_FREQ, ROT_FREQ = 5.0, 10.0
DURATIONS = [0.5, 0.625, 0.75, 0.875, 1.0, 1.25, 1.5, 1.75, 2.0]     # crans 1 → 9 (5 = 4 i. avant / 20 après)
# images clés du preset, en images par rapport au PEAK (= la coupe) : (image, valeur, infl. entrée, infl. sortie)
ENV = {
    "zoom":   [(-4, 0.0, 0.0, 0.125), (0, 1.0, 0.576, 0.436), (6, 0.0, 0.564, 0.0)],
    "pos":    [(-4, 0.0, 0.0, 0.756), (0, 1.0, 0.333, 0.311), (20, 0.0, 0.791, 0.0)],
    "rot":    [(0, 0.0, 0.0, 0.756), (2, 1.0, 0.333, 0.311), (20, 0.0, 0.791, 0.0)],
    "chroma": [(-2, 0.0, 0.0, 0.333), (2, 1.0, 0.594, 0.333), (8, 0.0, 1.0, 0.0)],
}
BEFORE, AFTER = 4, 20    # images avant / après le peak à la durée normale
SEED = 1234


def defaults():
    return {"actif": True, "sens": "out", "niveau": 3, "duree": 5}


def clean(cfg):
    d = defaults()
    if isinstance(cfg, dict):
        d.update({k: cfg[k] for k in d if k in cfg})
        if "sens" not in cfg and ("in" in cfg or "out" in cfg):       # ancien format (0.6.9)
            if cfg.get("out"):
                d["sens"], d["niveau"] = "out", cfg["out"]
            elif cfg.get("in"):
                d["sens"], d["niveau"] = "in", cfg["in"]
    d["actif"] = bool(d["actif"])
    d["sens"] = d["sens"] if d["sens"] in ("in", "out") else "out"
    d["niveau"] = max(1, min(5, int(d["niveau"] or 3)))
    d["duree"] = max(1, min(9, int(d["duree"] or 5)))
    return d


def _bez(u, o, i):
    """Courbe d'ease After Effects (vitesses nulles) : temps normalisé u → valeur 0..1."""
    x1, x2 = max(o, 1e-3), 1 - max(i, 1e-3)
    lo, hi = 0.0, 1.0
    for _ in range(22):
        s = (lo + hi) / 2
        x = 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s * s * x2 + s ** 3
        if x < u:
            lo = s
        else:
            hi = s
    s = (lo + hi) / 2
    return 3 * (1 - s) * s * s + s ** 3


def envelope(name, f):
    keys = ENV[name]
    if f <= keys[0][0] or f >= keys[-1][0]:
        return 0.0
    for a, b in zip(keys, keys[1:]):
        if a[0] <= f <= b[0]:
            u = (f - a[0]) / (b[0] - a[0])
            return a[1] + (b[1] - a[1]) * _bez(u, a[3], b[2])
    return 0.0


def _noise(x, seed):
    """Bruit lisse 1D dans [-1, 1] (comme le wiggle d'After Effects à 1 octave)."""
    i = math.floor(x)
    f = x - i

    def r(n):
        h = (n * 374761393 + seed * 668265263) & 0xFFFFFFFF
        h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
        v = ((h ^ (h >> 16)) & 0xFFFF) / 32767.5 - 1.0
        return math.copysign(0.6 + 0.4 * abs(v), v)       # toujours un vrai coup (jamais presque 0)
    s = f * f * f * (f * (f * 6 - 15) + 10)
    return r(i) + (r(i + 1) - r(i)) * s


def frame_params(t, cuts, cfg):
    """Paramètres de l'image à l'instant t : zoom, dx, dy, rotation (°), chromatique (px).
    Chaque coupe est le PEAK du shake ; les shakes qui se chevauchent s'additionnent."""
    zoom, dx, dy, rot, chroma = 1.0, 0.0, 0.0, 0.0, 0.0
    k = DURATIONS[cfg["duree"] - 1]
    z, pa, ca = LEVELS[cfg["niveau"]]
    zin = cfg["sens"] == "in"
    for n, c in enumerate(cuts):
        f = (t - c) * FPS_REF / k               # images depuis le peak, à la durée normale
        if f <= -BEFORE or f >= AFTER:
            continue
        seed = SEED + n * 101
        e = envelope("zoom", f) * (1 - z)
        zoom *= (1 + e) if zin else (1 - e)
        ep = envelope("pos", f) * pa
        if ep:
            x = (t - c) * POS_FREQ / k          # coup le plus fort pile au peak
            dx += ep * _noise(x, seed)
            dy += ep * _noise(x, seed + 31)
        er = envelope("rot", f) * ROT_AMP
        if er:
            rot += er * _noise((t - c) * ROT_FREQ / k, seed + 57)
        chroma += envelope("chroma", f) * ca
    return zoom, dx, dy, rot, chroma


def _reflect(i, n):
    p = 2 * n
    i = np.mod(i, p)
    return np.where(i >= n, p - 1 - i, i)


class _Warper:
    def __init__(self, w, h):
        self.w, self.h = w, h
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        self.xc = xs - (w - 1) / 2
        self.yc = ys - (h - 1) / 2

    def apply(self, img, zoom, dx, dy, rot, chroma):
        w, h = self.w, self.h
        a = math.radians(rot)
        ca, sa = math.cos(a) / zoom, math.sin(a) / zoom
        # image source = inverse de (zoom, rotation, déplacement) autour du centre
        x = self.xc - dx
        y = self.yc - dy
        sx = ca * x + sa * y + (w - 1) / 2
        sy = -sa * x + ca * y + (h - 1) / 2
        x0 = np.floor(sx)
        y0 = np.floor(sy)
        fx = (sx - x0)[..., None]
        fy = (sy - y0)[..., None]
        x0 = x0.astype(np.int32)
        y0 = y0.astype(np.int32)
        xa, xb = _reflect(x0, w), _reflect(x0 + 1, w)
        ya, yb = _reflect(y0, h), _reflect(y0 + 1, h)
        src = img.astype(np.float32)
        top = src[ya, xa] * (1 - fx) + src[ya, xb] * fx
        bot = src[yb, xa] * (1 - fx) + src[yb, xb] * fx
        out = top * (1 - fy) + bot * fy
        s = int(round(chroma))
        if s:
            idx = _reflect(np.arange(w) - s, w)
            out[..., 0] = out[:, idx, 0]
            idx = _reflect(np.arange(w) + s, w)
            out[..., 2] = out[:, idx, 2]
        return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def active(cfg, cuts):
    return clean(cfg)["actif"] and bool(cuts)


def apply(src, output, cuts, cfg, w, h, fps, total, is_cancelled=None, progress=None):
    """Repasse sur la vidéo src (sans son) et pose les shakes autour de chaque coupe."""
    cfg = clean(cfg)
    ff = audio.ffmpeg_exe()
    size = w * h * 3
    dec = subprocess.Popen([ff, "-hide_banner", "-loglevel", "error", "-i", str(src), "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           creationflags=audio._NO_WINDOW)
    enc = subprocess.Popen([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "16", "-pix_fmt", "yuv420p", str(output)],
                           stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=audio._NO_WINDOW)
    err = []
    threading.Thread(target=lambda: err.append(enc.stderr.read()), daemon=True).start()
    warper = _Warper(w, h)
    pool = ThreadPoolExecutor(max_workers=4)
    pending = []
    n = 0
    try:
        while True:
            if is_cancelled and is_cancelled():
                raise InterruptedError()
            buf = dec.stdout.read(size)
            if len(buf) < size:
                break
            p = frame_params(n / fps, cuts, cfg)
            if abs(p[0] - 1) < 1e-4 and abs(p[1]) < 0.05 and abs(p[2]) < 0.05 and abs(p[3]) < 0.01 and p[4] < 0.5:
                pending.append(buf)
            else:
                img = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
                pending.append(pool.submit(warper.apply, img, *p))
            while len(pending) > 8 or (pending and isinstance(pending[0], bytes)):
                x = pending.pop(0)
                enc.stdin.write(x if isinstance(x, bytes) else x.result().tobytes())
            n += 1
            if progress and n % 30 == 0:
                progress(min(1.0, n / max(1, total)), f"Shakes : image {n}/{total}")
        for x in pending:
            enc.stdin.write(x if isinstance(x, bytes) else x.result().tobytes())
        enc.stdin.close()
        if enc.wait() != 0:
            raise RuntimeError((err[0] if err else b"").decode("utf-8", "replace")[-800:] or "encodage impossible")
    except BaseException:
        for p in (dec, enc):
            try:
                p.kill()
            except OSError:
                pass
        raise
    finally:
        pool.shutdown(wait=False)
        try:
            dec.kill()
        except OSError:
            pass

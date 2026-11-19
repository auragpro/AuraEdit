"""Shakes « Hit Impulse » posés sur chaque coupe de l'edit.

Recréé à partir des réglages du preset Hit Impulse (pack Simple) : à chaque niveau 1x → 5x, un léger
zoom arrière avec bords en miroir, un tremblement de position (wiggle), un tremblement de rotation et
un décalage de couleurs (chromatique). OUT = le shake part de la coupe et retombe ; IN = il monte
jusqu'à la coupe. La durée (9 crans, 5 = normal) étire ou resserre tout l'effet.
"""
import math
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import audio

BASE_FPS = 25.0          # les images clés du preset sont comptées en images à 25 i/s
# niveau : (zoom mini, amplitude position px, décalage chromatique px)
LEVELS = {1: (0.97, 25, 5), 2: (0.95, 30, 6), 3: (0.90, 35, 7), 4: (0.85, 45, 8), 5: (0.80, 60, 9)}
ROT_AMP = 4.5            # degrés
POS_FREQ, ROT_FREQ = 5.0, 10.0
DURATIONS = [0.4, 0.55, 0.7, 0.85, 1.0, 1.25, 1.5, 1.75, 2.0]     # crans 1 → 9
# images clés (image, valeur 0..1, influence entrée, influence sortie)
ENV = {
    "zoom":   [(0, 0.0, 0.0, 0.125), (8, 1.0, 0.576, 0.436), (20, 0.0, 0.564, 0.0)],
    "pos":    [(0, 0.0, 0.0, 0.756), (8, 1.0, 0.333, 0.311), (48, 0.0, 0.791, 0.0)],
    "rot":    [(8, 0.0, 0.0, 0.756), (12, 1.0, 0.333, 0.311), (48, 0.0, 0.791, 0.0)],
    "chroma": [(4, 0.0, 0.0, 0.333), (12, 1.0, 0.594, 0.333), (24, 0.0, 1.0, 0.0)],
}
LENGTH = 48              # images (25 i/s) d'un shake complet, à la durée normale


def defaults():
    return {"actif": True, "in": 0, "out": 3, "duree": 5, "seed": 1234}


def clean(cfg):
    d = defaults()
    if isinstance(cfg, dict):
        d.update({k: cfg[k] for k in d if k in cfg})
    d["actif"] = bool(d["actif"])
    for k in ("in", "out"):
        d[k] = max(0, min(5, int(d[k] or 0)))
    d["duree"] = max(1, min(9, int(d["duree"] or 5)))
    d["seed"] = int(d["seed"] or 0) % 100000
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
        return ((h ^ (h >> 16)) & 0xFFFF) / 32767.5 - 1.0
    s = f * f * f * (f * (f * 6 - 15) + 10)
    return r(i) + (r(i + 1) - r(i)) * s


def frame_params(t, cuts, cfg):
    """Paramètres de l'image à l'instant t : zoom, dx, dy, rotation (°), chromatique (px)."""
    zoom, dx, dy, rot, chroma = 1.0, 0.0, 0.0, 0.0, 0.0
    k = DURATIONS[cfg["duree"] - 1]
    span = LENGTH / BASE_FPS * k
    for n, c in enumerate(cuts):
        if abs(t - c) > span:
            continue
        for side in ("out", "in"):
            lvl = cfg[side]
            if not lvl:
                continue
            tau = (t - c) if side == "out" else (c - t)
            if tau < 0:
                continue
            f = tau * BASE_FPS / k
            if f >= LENGTH:
                continue
            z, pa, ca = LEVELS[lvl]
            seed = cfg["seed"] + n * 101 + (7 if side == "in" else 0)
            zoom *= 1 - (1 - z) * envelope("zoom", f)
            ep = envelope("pos", f) * pa
            if ep:
                dx += ep * _noise(t * POS_FREQ, seed)
                dy += ep * _noise(t * POS_FREQ, seed + 31)
            er = envelope("rot", f) * ROT_AMP
            if er:
                rot += er * _noise(t * ROT_FREQ, seed + 57)
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
    cfg = clean(cfg)
    return cfg["actif"] and bool(cuts) and (cfg["in"] or cfg["out"])


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

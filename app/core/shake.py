"""Shakes « Hit Impulse » posés sur chaque coupe de l'edit.

Reproduit À L'IDENTIQUE à partir du preset Motion Bro : chaque version (IN 1x–5x, OUT 1x–5x) a été rendue
dans After Effects sur une grille de points, puis mesurée image par image (zoom, rotation, position,
décalage rouge/bleu). Le PEAK tombe pile sur la coupe ; durée normale : 4 images avant, 20 après (60 i/s).
"""
import math
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import audio

FPS_REF = 60.0           # le rendu de l'edit est à 60 i/s
DURATIONS = [0.5, 0.625, 0.75, 0.875, 1.0, 1.25, 1.5, 1.75, 2.0]     # crans 1 → 9 (5 = 4 i. avant / 20 après)
BEFORE, AFTER = 4, 20    # images (60 i/s) avant / après le peak à la durée normale
_DATA = None


def data():
    """Courbes mesurées image par image dans After Effects (voir app/assets/shake_hit_impulse.json)."""
    global _DATA
    if _DATA is None:
        import json
        import sys
        from pathlib import Path
        cands = [Path(__file__).resolve().parents[1] / "assets" / "shake_hit_impulse.json"]
        if getattr(sys, "_MEIPASS", None):
            cands.append(Path(sys._MEIPASS) / "app" / "assets" / "shake_hit_impulse.json")
        for c in cands:
            if c.is_file():
                _DATA = json.loads(c.read_text(encoding="utf-8"))
                break
        else:
            raise RuntimeError("Données du shake introuvables (shake_hit_impulse.json)")
    return _DATA


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


def _source_time(dt, k, D):
    """Temps dans le preset (s) pour un écart dt (s) au peak : 4 i. avant → début..peak, 20 i. après → peak..fin."""
    peak, deb, fin = D["peak"], D["debut"], D["fin"]
    if dt < 0:
        return peak + dt * (peak - deb) / (BEFORE / FPS_REF * k)
    return peak + dt * (fin - peak) / (AFTER / FPS_REF * k)


def _sample(frames, fps, s):
    x = s * fps
    i = int(math.floor(x))
    if i < 0 or i + 1 >= len(frames):
        return None
    u = x - i
    a, b = frames[i], frames[i + 1]
    return [p + (q - p) * u for p, q in zip(a, b)]


def frame_params(t, cuts, cfg):
    """Matrice 3x3 (sortie = M·entrée) et décalage rouge-bleu à l'instant t. Chaque coupe = PEAK ;
    les shakes qui se chevauchent se combinent."""
    D = data()
    frames = D["presets"][f"{cfg['niveau']}x_{'In' if cfg['sens'] == 'in' else 'Out'}"]
    k = DURATIONS[cfg["duree"] - 1]
    M = np.eye(3)
    rb = np.zeros(2)
    lo, hi = -BEFORE / FPS_REF * k, AFTER / FPS_REF * k
    for c in cuts:
        dt = t - c
        if dt <= lo or dt >= hi:
            continue
        v = _sample(frames, D["fps"], _source_time(dt, k, D))
        if v is None:
            continue
        m = np.array([[v[0], v[1], v[2]], [v[3], v[4], v[5]], [0, 0, 1]])
        M = m @ M
        rb += (v[6], v[7])
    return M, rb


def _reflect(i, n):
    p = 2 * n
    i = np.mod(i, p)
    return np.where(i >= n, p - 1 - i, i)


class _Warper:
    def __init__(self, w, h):
        self.w, self.h = w, h
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        self.xs, self.ys = xs, ys

    def _bilinear(self, ch, sx, sy):
        w, h = self.w, self.h
        x0 = np.floor(sx)
        y0 = np.floor(sy)
        fx = sx - x0
        fy = sy - y0
        x0 = x0.astype(np.int32)
        y0 = y0.astype(np.int32)
        xa, xb = _reflect(x0, w), _reflect(x0 + 1, w)
        ya, yb = _reflect(y0, h), _reflect(y0 + 1, h)
        top = ch[ya, xa] * (1 - fx) + ch[ya, xb] * fx
        bot = ch[yb, xa] * (1 - fx) + ch[yb, xb] * fx
        return top * (1 - fy) + bot * fy

    def apply(self, img, M, rb):
        """img : image d'entrée. Bords en miroir comme le preset. Rouge décalé de +rb/2, bleu de -rb/2."""
        # coordonnées du coin des pixels (convention After Effects : centre du pixel = i + 0.5)
        Mi = np.linalg.inv(M)
        src = img.astype(np.float32)
        out = np.empty_like(src)
        for c, sh in ((0, rb / 2), (1, np.zeros(2)), (2, -rb / 2)):
            px = self.xs + 0.5 - float(sh[0])
            py = self.ys + 0.5 - float(sh[1])
            sx = Mi[0, 0] * px + Mi[0, 1] * py + Mi[0, 2] - 0.5
            sy = Mi[1, 0] * px + Mi[1, 1] * py + Mi[1, 2] - 0.5
            out[..., c] = self._bilinear(src[..., c], sx, sy)
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
            M, rb = frame_params(n / fps, cuts, cfg)
            if np.abs(M - np.eye(3)).max() < 1e-5 and np.abs(rb).max() < 0.05:
                pending.append(buf)
            else:
                img = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
                pending.append(pool.submit(warper.apply, img, M, rb))
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

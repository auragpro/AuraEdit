"""Edit auto : on regarde chaque plan de l'edit fini et on reconnaît ce que c'est
(quel couteau, un kunai, un dash main gauche / droite...), en le comparant à tes propres clips.

On compare surtout le bas de l'image (là où sont l'arme, le couteau, la main du dash), moitié gauche et
moitié droite séparément : un dash main gauche et un dash main droite ne se ressemblent donc pas.
"""
import subprocess
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from . import audio, vclip

SW, SH = 160, 90
EDIT_FPS = 10


def _grab(path, t):
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                        *vclip.input_args(path, ss=max(0.0, t)), "-frames:v", "1", "-vf",
                        f"scale={SW}:{SH},format=rgb24", "-f", "rawvideo", "-"],
                       capture_output=True, creationflags=audio._NO_WINDOW)
    if len(p.stdout) < SW * SH * 3:
        return None
    return np.frombuffer(p.stdout[:SW * SH * 3], np.uint8).reshape(SH, SW, 3)


def _image(file):
    img = cv2.imread(str(file))
    if img is None:
        return None
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), (SW, SH), interpolation=cv2.INTER_AREA)


def desc(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    hists = []
    for x0, x1 in ((0, SW // 2), (SW // 2, SW)):
        h = cv2.calcHist([np.ascontiguousarray(hsv[SH // 2:, x0:x1])], [0, 1], None, [18, 4],
                         [0, 180, 0, 256]).ravel()
        hists.append(h / (h.sum() + 1e-6))
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)[SH // 2:]
    g = cv2.resize(g, (32, 9), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    g = (g - g.mean()) / (g.std() + 1e-6)
    return np.concatenate(hists), g


def sim(a, b):
    hi = np.minimum(a[0], b[0]).sum() / 2                    # 0..1
    co = float(np.dot(a[1], b[1]) / len(a[1]))               # -1..1
    return 0.65 * hi + 0.35 * (co + 1) / 2


def edit_frames(path):
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(path), "-an",
                        "-vf", f"fps={EDIT_FPS},scale={SW}:{SH},format=rgb24", "-f", "rawvideo", "-"],
                       capture_output=True, creationflags=audio._NO_WINDOW)
    n = len(p.stdout) // (SW * SH * 3)
    return np.frombuffer(p.stdout[:n * SW * SH * 3], np.uint8).reshape(n, SH, SW, 3)


def analyse(edit, bounds, classes, remaps, durations, progress=None, cancelled=None):
    """classes : {clé: {"clips": [...], "image": fichier ou None}}.
    Renvoie, pour chaque plan, la liste des clés triées du plus ressemblant au moins ressemblant."""
    jobs = []                                                 # (clé, chemin, t)
    for key, c in classes.items():
        for clip in c["clips"][:5]:
            rm = remaps.get(clip)
            d = durations.get(clip) or 2.0
            ts = [float(rm["debut"]) + 0.1] if rm else []
            ts += [d * 0.35, d * 0.65]
            jobs += [(key, clip, t) for t in ts]
    refs = {k: [] for k in classes}
    for key, c in classes.items():
        img = _image(c["image"]) if c.get("image") else None
        if img is not None:
            refs[key].append(desc(img))
    done = 0
    with ThreadPoolExecutor(6) as ex:
        futs = [(key, ex.submit(_grab, clip, t)) for key, clip, t in jobs]
        for key, f in futs:
            img = f.result()
            if img is not None:
                refs[key].append(desc(img))
            done += 1
            if progress and done % 4 == 0:
                progress(0.8 * done / max(1, len(futs)), "J'apprends tes clips...")
            if cancelled and cancelled():
                raise InterruptedError()
    if progress:
        progress(0.8, "Je regarde l'edit...")
    frames = edit_frames(edit)
    out = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        idx = sorted({min(len(frames) - 1, max(0, int((a + (b - a) * f) * EDIT_FPS))) for f in (0.3, 0.5, 0.75)})
        ds = [desc(frames[j]) for j in idx] if len(frames) else []
        scores = {}
        for key, rl in refs.items():
            if not rl or not ds:
                scores[key] = -1
                continue
            scores[key] = float(np.mean([max(sim(d, r) for r in rl) for d in ds]))
        out.append(sorted(scores, key=lambda k: -scores[k]))
    if progress:
        progress(1.0, "Terminé")
    return out

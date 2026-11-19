"""Time remap des clips de couteau, comme dans After Effects.

3 keyframes de Time Remap :
  1. au début du clip  -> la frame où le perso sort le couteau (plus de mains à l'écran)
  2. presque à la fin  -> la frame « couteau sorti » (jusqu'où va le time remap)
  3. à la fin          -> copie de la 1re : retour en arrière (reverse)
Entre 1 et 2 : courbe 1 ; entre 2 et 3 : courbe 2 (format « x1, y1, x2, y2 » comme Flow / AE).
Le frame blending mélange les frames voisines : ralenti fluide, et flou de mouvement dans le reverse.
"""
import json
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import audio
from .project import config_dir

FPS = 60
W, H = 1920, 1080
# zone des mains / de l'arme (en bas à droite) utilisée pour reconnaître le couteau
REGION = "crop=iw*0.45:ih*0.55:iw*0.55:ih*0.45,scale=96:66"
RW, RH = 96, 66

DEFAULTS = {
    "courbe1": [0.39, 0.59, 0.26, 1.0],
    "courbe2": [0.33, 0.0, 0.74, 0.8],
    "duree_ralenti": 1.0,      # secondes entre la keyframe 1 et la 2
    "frames_retour": 6,        # frames entre la keyframe 2 et la 3 (le reverse)
    "blending": True,
    "couteaux": {},            # {nom: {"image": chemin, "duree": secondes entre début et fin}}
}


# ------------------------------------------------------------- réglages ----

def _file():
    return config_dir() / "timeremap.json"


def load():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    if not isinstance(cfg.get("couteaux"), dict):
        cfg["couteaux"] = {}
    return cfg


def save(cfg):
    try:
        _file().write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def knife_dir():
    d = config_dir() / "couteaux"
    d.mkdir(parents=True, exist_ok=True)
    return d


def parse_curve(text):
    """'0.39, 0.59, 0.26, 1' -> [0.39, 0.59, 0.26, 1.0] (None si illisible)."""
    nums = re.findall(r"-?\d+(?:[.,]\d+)?", text or "")
    if len(nums) != 4:
        return None
    vals = [float(n.replace(",", ".")) for n in nums]
    vals[0] = min(max(vals[0], 0.0), 1.0)
    vals[2] = min(max(vals[2], 0.0), 1.0)
    return vals


def curve_text(c):
    return ", ".join(f"{v:g}" for v in c)


# --------------------------------------------------------------- courbes ----

def ease(curve, u):
    """Courbe de Bézier cubique (0,0)-(x1,y1)-(x2,y2)-(1,1) : temps u (0..1) -> valeur."""
    x1, y1, x2, y2 = curve
    u = min(max(u, 0.0), 1.0)
    lo, hi = 0.0, 1.0
    t = u
    for _ in range(40):
        t = (lo + hi) / 2
        x = 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t ** 2 * x2 + t ** 3
        if x < u:
            lo = t
        else:
            hi = t
    return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t ** 2 * y2 + t ** 3


def timing(cfg):
    t1 = max(0.05, float(cfg.get("duree_ralenti", 1.0)))
    t2 = max(1, int(cfg.get("frames_retour", 6))) / FPS
    return t1, t2


def source_time(tau, start, end, cfg):
    """Instant de sortie tau (s) -> instant dans le clip source (s)."""
    t1, t2 = timing(cfg)
    if tau <= t1:
        return start + (end - start) * ease(cfg["courbe1"], tau / t1)
    return end + (start - end) * ease(cfg["courbe2"], (tau - t1) / t2)


# ------------------------------------------------------------- détection ----

def _decode(args, size):
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *args,
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, creationflags=audio._NO_WINDOW)
    data = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(data) // size
    return data[:n * size].reshape(n, size)


def _norm(a):
    a = a.astype(np.float32)
    a -= a.mean(axis=-1, keepdims=True)
    a /= np.linalg.norm(a, axis=-1, keepdims=True) + 1e-6
    return a


def region_frames(path):
    return _decode(["-i", str(path), "-an", "-vf", f"fps={FPS},{REGION}"], RW * RH * 3)


def region_image(path):
    f = _decode(["-i", str(path), "-vf", REGION, "-frames:v", "1"], RW * RH * 3)
    return f[0] if len(f) else None


KILL_REGION = "crop=iw*0.2:ih*0.2:iw*0.4:ih*0.68,scale=40:24"


def find_kills(path):
    """Instants (frames) où la bannière de kill apparaît."""
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(path), "-an",
                        "-vf", f"fps={FPS},{KILL_REGION}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True, creationflags=audio._NO_WINDOW)
    data = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(data) // (40 * 24)
    if n < 6:
        return []
    k = data[:n * 960].reshape(n, 960).astype(np.int16)
    d = np.zeros(n)
    d[2:] = np.abs(k[2:] - k[:-2]).mean(axis=1)
    med = np.median(d)
    mad = np.median(np.abs(d - med)) + 1e-6
    thr = max(med + 6 * mad, med + 4)
    kills, last = [], -FPS
    for i in np.nonzero(d > thr)[0]:
        if i - last > FPS // 2:              # une bannière = un kill (on ignore la suite de l'animation)
            kills.append(int(i))
        last = i
    return kills


class Analysis:
    """Résultat de l'analyse d'un clip : kills trouvés + keyframes pour le kill choisi."""

    def __init__(self, path, knife=None):
        self.knife = knife or {}
        self.frames = region_frames(path)
        self.n = len(self.frames)
        if self.n < 4:
            raise ValueError("Vidéo illisible ou trop courte.")
        self.F = _norm(self.frames)
        self.kills = [k for k in find_kills(path) if k < self.n - 2]
        self.sims = None
        img = self.knife.get("image")
        if img and Path(img).is_file():
            tmpl = region_image(img)
            if tmpl is not None:
                self.sims = self.F @ _norm(tmpl[None])[0]
        self.length = self.n / FPS

    def keyframes(self, kill_index=-1):
        """(début, fin) en secondes. début = 1re frame sans le couteau après le kill choisi."""
        F, n = self.F, self.n
        if self.kills:
            kill = self.kills[kill_index]
            ref = F[max(0, kill - 6):kill + 1].mean(axis=0)          # le couteau au moment du kill
            ref /= np.linalg.norm(ref) + 1e-6
            hi = min(n, kill + 3 * FPS)
            sim = F[kill:hi] @ ref
            base = float(np.median(F[max(0, kill - 15):kill + 1] @ ref))
            low = float(sim.min())
            if base - low > 0.12:
                thr = base - 0.6 * (base - low)
                start = kill + int(np.argmax(sim <= thr))
            else:
                start = kill + int(np.argmin(sim))
        else:
            # pas de kill trouvé : le plus gros changement dans la zone des mains
            diff = np.abs(np.diff(self.frames.astype(np.int16), axis=0)).mean(axis=1)
            k = max(1, FPS // 10)
            start = int(np.argmax(np.convolve(diff, np.ones(k) / k, mode="same")))
            ref, base, low = F[max(0, start - 10)], 1.0, 0.0
        start = min(start, n - 2)

        duree = self.knife.get("duree")
        if duree:
            end = start + int(round(duree * FPS))
        elif self.sims is not None and start + 2 < n:
            after = self.sims[start + 2:]
            end = start + 2 + int(np.argmax(after >= float(after.max()) * 0.92))
        else:
            # le couteau revient : la zone redevient comme au moment du kill
            sim = F[start + 3:min(n, start + 3 * FPS)] @ ref
            back = np.nonzero(sim >= base - 0.2 * (base - low))[0] if len(sim) else []
            end = start + 3 + int(back[0]) if len(back) else start + FPS // 2
        end = min(max(end, start + 1), n - 1)
        return start / FPS, end / FPS


def detect(path, knife=None):
    a = Analysis(path, knife)
    s, e = a.keyframes()
    return s, e, a.length


def grab_png(path, t, width=480):
    """Image PNG (octets) de la vidéo à l'instant t, pour l'aperçu."""
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, t):.3f}",
                        "-i", str(path), "-frames:v", "1", "-vf", f"scale={width}:-2",
                        "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True, creationflags=audio._NO_WINDOW)
    return p.stdout


def save_knife_image(name, path, t):
    """Garde la frame « couteau sorti » comme image de référence du couteau."""
    target = knife_dir() / (re.sub(r'[<>:"/\\|?*]', "_", name) + ".png")
    subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0, t):.3f}",
                    "-i", str(path), "-frames:v", "1", str(target)],
                   capture_output=True, creationflags=audio._NO_WINDOW)
    return str(target) if target.is_file() else None


# ----------------------------------------------------------------- rendu ----

def render(path, start, end, cfg, output, is_cancelled=None):
    """Fabrique la partie time-remappée du clip (1920x1080, 60 i/s, sans son)."""
    t1, t2 = timing(cfg)
    total = t1 + t2
    n_out = max(2, int(round(total * FPS)) + 1)
    blending = bool(cfg.get("blending", True))

    # instants source nécessaires pour chaque frame de sortie
    sub = 7 if blending else 1
    plan = []
    for k in range(n_out):
        tau = min(k / FPS, total)
        if blending:
            taus = [min(max(tau + (j / (sub - 1) - 0.5) / FPS, 0), total) for j in range(sub)]
        else:
            taus = [tau]
        plan.append([source_time(x, start, end, cfg) for x in taus])

    lo = max(0.0, min(min(p) for p in plan) - 2 / FPS)
    hi = max(max(p) for p in plan) + 2 / FPS
    vf = (f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1")
    frames = _decode(["-ss", f"{lo:.3f}", "-i", str(path), "-t", f"{hi - lo:.3f}", "-an", "-vf", vf],
                     W * H * 3)
    if not len(frames):
        raise ValueError(f"Impossible de lire {Path(path).name}")
    last = len(frames) - 1

    with tempfile.TemporaryFile() as err:
        enc = subprocess.Popen([audio.ffmpeg_exe(), "-y", "-hide_banner", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset",
                                "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(output)],
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err,
                               creationflags=audio._NO_WINDOW)
        try:
            for times in plan:
                if is_cancelled and is_cancelled():
                    raise InterruptedError()
                weights = {}
                for s in times:                       # mélange des frames voisines
                    x = min(max((s - lo) * FPS, 0), last)
                    i = int(x)
                    f = x - i
                    weights[i] = weights.get(i, 0) + (1 - f)
                    if f > 0 and i + 1 <= last:
                        weights[i + 1] = weights.get(i + 1, 0) + f
                tot = sum(weights.values())
                if len(weights) == 1:
                    img = frames[next(iter(weights))]
                else:
                    acc = np.zeros(W * H * 3, dtype=np.float32)
                    for i, w in weights.items():
                        acc += frames[i].astype(np.float32) * (w / tot)
                    img = np.clip(acc + 0.5, 0, 255).astype(np.uint8)
                enc.stdin.write(img.tobytes())
            enc.stdin.close()
        except (InterruptedError, BrokenPipeError, OSError):
            enc.kill()
            enc.wait()
            raise
        if enc.wait() != 0:
            err.seek(0)
            raise ValueError(err.read()[-800:].decode("utf-8", "replace"))
    return total

"""Time remap des clips de couteau, comme dans After Effects.

3 keyframes de Time Remap :
  1. au début du clip  -> la frame où le perso sort le couteau (plus de mains à l'écran)
  2. presque à la fin  -> la frame « couteau sorti » (jusqu'où va le time remap)
  3. à la fin          -> copie de la 1re : retour en arrière (reverse)
Entre 1 et 2 : courbe 1 ; entre 2 et 3 : courbe 2 (format « x1, y1, x2, y2 » comme Flow / AE).
Pixel Motion : images intermédiaires calculées (flux optique) pour un ralenti fluide sans images dédoublées.
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
    "blending_mode": "motion", # "motion" (Pixel Motion), "mix" (Frame Mix) ou "off"
    "mode_v2": False,          # passage automatique au Pixel Motion (une seule fois)
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
    if not cfg.get("mode_v2"):                     # le Frame Mix dédouble les images : Pixel Motion par défaut
        cfg["blending_mode"] = "motion"
        cfg["blending"] = True
        cfg["mode_v2"] = True
    return cfg


def save(cfg):
    try:
        _file().write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def _clips_file():
    return config_dir() / "time_remap_clips.json"


def clip_remaps():
    """{chemin du clip: {"couteau", "debut", "fin"}} — gardé pour tous les projets."""
    try:
        d = json.loads(_clips_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_clip_remap(path, data):
    d = clip_remaps()
    d[str(path)] = data
    try:
        _clips_file().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
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

BLEND_MODES = {"motion": "Pixel Motion (le plus fluide, recommandé)",
               "mix": "Frame Mix (mélange 2 images, peut dédoubler)",
               "off": "Aucun"}


def blend_mode(cfg):
    m = cfg.get("blending_mode")
    if m in BLEND_MODES:
        return m
    return "mix" if cfg.get("blending", True) else "off"


def source_fps(path):
    """Images par seconde réelles du clip (pour ne pas dupliquer d'images)."""
    out = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True,
                         creationflags=audio._NO_WINDOW).stderr.decode("utf-8", "replace")
    for line in out.splitlines():
        if "Video:" in line:
            m = re.search(r"(\d+(?:\.\d+)?) fps", line) or re.search(r"(\d+(?:\.\d+)?) tbr", line)
            if m:
                f = float(m.group(1))
                if 10 <= f <= 400:
                    return f
    return 60.0


def render(path, start, end, cfg, output, is_cancelled=None, progress=None):
    """Comme _render ; si le Pixel Motion échoue, on refait automatiquement en Frame Mix."""
    if blend_mode(cfg) == "motion":
        try:
            return _render(path, start, end, cfg, output, is_cancelled, progress)
        except InterruptedError:
            raise
        except Exception:
            cfg = dict(cfg, blending_mode="mix")
    return _render(path, start, end, cfg, output, is_cancelled, progress)


PAD = 4          # images source en plus de chaque côté d'un morceau (pour que l'interpolation soit identique)


def _decode_parallel(path, lo, sfps, factor, vf, needed, last_needed, is_cancelled, progress, label):
    """Décode (et interpole) le passage en plusieurs morceaux EN MÊME TEMPS, un par cœur du processeur.

    Le filtre d'interpolation de ffmpeg n'utilise qu'un cœur : en coupant le passage en morceaux qui se
    chevauchent de quelques images, chaque image calculée est la même qu'en un seul morceau, mais
    on va jusqu'à N fois plus vite."""
    import os
    import threading
    n_src = last_needed // factor + 2                       # images source utiles
    workers = max(1, min(8, (os.cpu_count() or 2) - 1, n_src // 12))
    bounds = [round(i * n_src / workers) for i in range(workers + 1)]
    size = W * H * 3
    frames, errors, done = {}, [], [0]
    lock = threading.Lock()
    procs = []

    def run(j):
        m0, m1 = bounds[j], bounds[j + 1]
        s0 = max(0, m0 - PAD)
        keep0, keep1 = m0 * factor, (m1 * factor if j < workers - 1 else last_needed + 1)
        base = s0 * factor
        errf = tempfile.TemporaryFile()
        dec = subprocess.Popen([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                                "-ss", f"{lo + s0 / sfps:.6f}", "-i", str(path),
                                "-t", f"{(m1 + PAD - s0) / sfps:.6f}", "-an", "-vf", vf,
                                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                               stdout=subprocess.PIPE, stderr=errf, creationflags=audio._NO_WINDOW)
        with lock:
            procs.append(dec)
        try:
            k = 0
            while base + k < keep1:
                if is_cancelled and is_cancelled():
                    return
                buf = dec.stdout.read(size)
                if len(buf) < size:
                    break
                g = base + k
                if g >= keep0 and g in needed:
                    with lock:
                        frames[g] = np.frombuffer(buf, dtype=np.uint8)
                if g >= keep0:
                    with lock:
                        done[0] += 1
                k += 1
        finally:
            dec.kill()
            dec.wait()
            errf.seek(0)
            msg = errf.read()[-600:].decode("utf-8", "replace")
            errf.close()
            if msg.strip():
                with lock:
                    errors.append(msg)

    threads = [threading.Thread(target=run, args=(j,), daemon=True) for j in range(workers)]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        for t in threads:
            t.join(0.25)
        if is_cancelled and is_cancelled():
            for p in procs:
                p.kill()
            for t in threads:
                t.join()
            raise InterruptedError()
        if progress:
            progress(0.85 * min(1.0, done[0] / (last_needed + 1)),
                     f"{label} : calcul des images {done[0]}/{last_needed + 1} ({workers} cœurs)")
    if not frames:
        raise ValueError(f"Impossible de lire {Path(path).name}\n" + "".join(errors[-1:]))
    return frames, max(frames)


def _render(path, start, end, cfg, output, is_cancelled=None, progress=None):
    """Fabrique la partie time-remappée du clip (1920x1080, 60 i/s, sans son).

    Frame Mix : chaque image de sortie = mélange des 2 images source voisines (comme After Effects).
    Pixel Motion : le clip est d'abord interpolé par flux optique (images intermédiaires calculées)."""
    t1, t2 = timing(cfg)
    total = t1 + t2
    n_out = max(2, int(round(total * FPS)) + 1)
    mode = blend_mode(cfg)
    times = [source_time(min(k / FPS, total), start, end, cfg) for k in range(n_out)]

    sfps = source_fps(path)
    # Pixel Motion : on vise ~240 images/s de source pour un ralenti sans saccade
    factor = max(2, min(6, int(round(240 / sfps)))) if mode == "motion" else 1
    rate = sfps * factor                                     # images par seconde après interpolation
    samples = [[t] for t in times]                 # une seule image par image de sortie : pas de flou
    flat = [x for ss in samples for x in ss]
    lo = max(0.0, min(flat) - 2 / sfps)
    hi = max(flat) + 2 / sfps
    pos = [[max(0.0, (x - lo) * rate) for x in ss] for ss in samples]
    needed = set()
    for ss in pos:
        for x in ss:
            i = int(x)
            if mode == "off":
                needed.add(int(round(x)))
            else:
                needed.update((i, i + 1))
    last_needed = max(needed)

    vf = f"fps={sfps:g}"
    if mode == "motion":
        vf += f",minterpolate=fps={rate:g}:mi_mode=mci:mc_mode=obmc:me_mode=bidir"
    vf += f",scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    label = "Pixel Motion" if mode == "motion" else "time remap"
    frames, lastframe = _decode_parallel(path, lo, sfps, factor, vf, needed, last_needed,
                                         is_cancelled, progress, label)
    avail = sorted(frames)

    def frame(i):
        if i in frames:
            return frames[i]
        return frames[min(avail, key=lambda a: abs(a - i))]

    with tempfile.TemporaryFile() as err:
        enc = subprocess.Popen([audio.ffmpeg_exe(), "-y", "-hide_banner", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset",
                                "medium", "-crf", "10", "-pix_fmt", "yuv420p", str(output)],
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err,
                               creationflags=audio._NO_WINDOW)
        try:
            top = float(lastframe if lastframe is not None else 0)
            for k, ss in enumerate(pos):
                if is_cancelled and is_cancelled():
                    raise InterruptedError()
                if progress and k % 8 == 0:
                    progress(0.85 + 0.15 * k / len(pos), f"{label} : assemblage {k}/{len(pos)}")
                x = min(max(ss[0], 0.0), top)
                if mode == "off":
                    img = frame(int(round(x)))
                else:
                    i = int(x)
                    f = x - i
                    if f < 0.02 or (i + 1) not in frames:
                        img = frame(i)
                    elif f > 0.98:
                        img = frame(i + 1)
                    else:                          # Frame Mix : 2 images voisines seulement
                        a = frame(i).astype(np.float32)
                        a *= 1 - f
                        a += frame(i + 1).astype(np.float32) * f
                        img = np.clip(a + 0.5, 0, 255).astype(np.uint8)
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

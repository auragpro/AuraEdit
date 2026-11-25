"""Time remap des clips de couteau, comme dans After Effects.

3 keyframes de Time Remap :
  1. la 1re frame où le perso sort le couteau (après avoir rangé son arme, juste après le kill)
  2. le flick away + 20 frames (jusqu'où va le time remap)
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

from . import audio, vclip
from .project import config_dir

FPS = 60
W, H = 1920, 1080
# zone des mains / de l'arme (en bas à droite) utilisée pour reconnaître le couteau
REGION = "crop=iw*0.45:ih*0.55:iw*0.55:ih*0.45,scale=96:66"
def remove_clip_remap(path):
    """Enlève le time remap de ce clip (il redevient un clip normal)."""
    d = clip_remaps()
    if d.pop(str(path), None) is not None:
        try:
            _clips_file().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass


def _starts_file():
    return config_dir() / "debut_clips.json"


def clip_starts():
    """{chemin du clip: seconde où il commence} pour les clips sans time remap."""
    try:
        d = json.loads(_starts_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_clip_start(path, t):
    d = clip_starts()
    if t is None or t <= 0:
        d.pop(str(path), None)
    else:
        d[str(path)] = round(float(t), 4)
    try:
        _starts_file().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


RW, RH = 96, 66

DEFAULTS = {
    "courbe1": [0.39, 0.59, 0.26, 1.0],
    "courbe2": [0.33, 0.0, 0.74, 0.8],
    "duree_ralenti": 1.0,      # secondes entre la keyframe 1 et la 2
    "frames_retour": 7,        # frames entre la keyframe 2 et la 3 (le reverse)
    "retour7": False,          # passage du reverse à 7 frames sur tous les clips (une seule fois)
    "blending": True,
    "blending_mode": "motion", # "motion" (Pixel Motion), "mix" (Frame Mix) ou "off"
    "mode_v2": False,          # passage automatique au Pixel Motion (une seule fois)
    "couteaux": {},            # {nom: {"image": chemin, "duree": secondes entre début et fin}}
    "kunai_reglages": {},      # réglages propres aux kunais (courbes, durées, blending, durée apprise)
    "courbes_perso": [],
    "dashback_reglages": {},   # réglages propres aux dash back
    "dismiss_reglages": {},    # réglages propres aux dismiss       # courbes enregistrées : [{"nom", "c1", "c2"}]
}
COURBES_BASE = [
    {"nom": "Par défaut", "c1": [0.39, 0.59, 0.26, 1.0], "c2": [0.33, 0.0, 0.74, 0.8]},
    {"nom": "Linéaire", "c1": [0.0, 0.0, 1.0, 1.0], "c2": [0.0, 0.0, 1.0, 1.0]},
    {"nom": "Doux", "c1": [0.33, 0.0, 0.67, 1.0], "c2": [0.33, 0.0, 0.67, 1.0]},
]
HAND_TYPES = ("kunai", "dashback", "dismiss")     # time remap « main » : part au kill, durée retenue
KUNAI_KEYS = ("courbe1", "courbe2", "duree_ralenti", "frames_retour", "blending", "blending_mode")


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
    if not cfg.get("retour7"):                     # reverse à 7 frames partout (une seule fois)
        cfg["frames_retour"] = 7
        for kind in HAND_TYPES:
            if isinstance(cfg.get(f"{kind}_reglages"), dict):
                cfg[f"{kind}_reglages"]["frames_retour"] = 7
        cfg["retour7"] = True
        save(cfg)
        d = clip_remaps()
        for v in d.values():
            if isinstance(v, dict):
                v["retour"], v["r7"] = 7, True
        try:
            _clips_file().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    return cfg


def cfg_for(data, cfg=None):
    """Réglages à utiliser pour un time remap : ceux des kunais si c'est un kunai."""
    base = cfg or load()
    merged = dict(base)
    if isinstance(data, dict) and data.get("type") in HAND_TYPES:
        k = base.get(f"{data['type']}_reglages") or {}
        merged.update({key: k[key] for key in KUNAI_KEYS if key in k})
    if isinstance(data, dict):                     # réglages propres à ce clip (s'il en a)
        if data.get("ralenti"):
            merged["duree_ralenti"] = float(data["ralenti"])
        if data.get("retour") and data.get("r7"):     # avant la 0.9.6 : on repasse au reverse à 7 frames
            merged["frames_retour"] = int(data["retour"])
    return merged


def save_kunai(merged, kind="kunai"):
    """Garde les réglages kunai / dash back / dismiss (pris dans un cfg fusionné) sans toucher à ceux des clips."""
    base = load()
    k = dict(base.get(f"{kind}_reglages") or {})
    k.update({key: merged[key] for key in KUNAI_KEYS if key in merged})
    if merged.get("duree_kunai"):
        k["duree"] = merged["duree_kunai"]
    base[f"{kind}_reglages"] = k
    save(base)


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
    """Code de courbe -> [x1, y1, x2, y2] (None si illisible). Accepte les codes copiés de Flow
    (After Effects) et le CSS : '.69,0,.31,1', 'cubic-bezier(0.69, 0, 0.31, 1)', '[0.69,0,0.31,1]',
    '0,69 ; 0 ; 0,31 ; 1' (virgule décimale à la française)."""
    t = (text or "").replace("cubic-bezier", "")
    nums = re.findall(r"-?(?:\d+\.\d*|\.\d+|\d+)", t)
    if len(nums) != 4 and ";" in t:                 # 0,69 ; 0 ; 0,31 ; 1
        nums = [n.strip().replace(",", ".") for n in t.split(";") if n.strip()]
        nums = [re.sub(r"[^0-9.\-]", "", n) for n in nums]
    if len(nums) != 4:
        return None
    try:
        vals = [float(n) for n in nums]
    except ValueError:
        return None
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
    t2 = max(1, int(cfg.get("frames_retour", 7))) / FPS
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
    return _decode([*vclip.input_args(path), "-an", "-vf", f"fps={FPS},{REGION}"], RW * RH * 3)


def region_image(path):
    f = _decode([*vclip.input_args(path), "-vf", REGION, "-frames:v", "1"], RW * RH * 3)
    return f[0] if len(f) else None


KILL_REGION = "crop=iw*0.2:ih*0.2:iw*0.4:ih*0.68,scale=40:24"


def find_kills(path):
    """Instants (frames) où la bannière de kill apparaît."""
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *vclip.input_args(path), "-an",
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


GLOBAL = "crop=iw*0.6:ih*0.5:iw*0.2:ih*0.15,scale=64:36"     # centre de l'image (sans le HUD) pour le flick
FLICK_FRAMES = 20                                              # keyframe 2 = flick away + 20 frames


def global_frames(path):
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *vclip.input_args(path), "-an",
                        "-vf", f"fps={FPS},{GLOBAL}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True, creationflags=audio._NO_WINDOW)
    data = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(data) // (64 * 36)
    return data[:n * 64 * 36].reshape(n, 64 * 36).astype(np.float32)


class Analysis:
    """Résultat de l'analyse d'un clip : kills trouvés + keyframes pour le kill choisi.

    Keyframe 1 : bannière de kill -> on recule jusqu'à l'arme (avant le kill) -> on avance jusqu'à la
                 1re frame où le couteau sort (après que l'arme est rangée).
    Keyframe 2 : le flick away (gros mouvement de toute l'image) + 20 frames."""

    def __init__(self, path, knife=None):
        self.knife = knife or {}
        self.frames = region_frames(path)
        self.n = len(self.frames)
        if self.n < 4:
            raise ValueError("Vidéo illisible ou trop courte.")
        self.F = _norm(self.frames)
        self.kills = [k for k in find_kills(path) if k < self.n - 2]
        self.length = self.n / FPS
        # changement de la zone des mains par rapport aux frames juste avant
        n = self.n
        self.chg = np.zeros(n)
        for i in range(10, n):
            ref = self.F[i - 10:i - 2].mean(axis=0)
            self.chg[i] = 1 - float(self.F[i] @ ref) / (np.linalg.norm(ref) + 1e-6)
        # mouvement de toute l'image (flick away)
        G = global_frames(path)
        m = np.zeros(n)
        k = min(n, len(G))
        if k > 1:
            m[1:k] = np.abs(np.diff(G[:k], axis=0)).mean(axis=1)
        for i in range(1, n):                       # clips à 120 i/s : une frame sur deux est un doublon
            if m[i] < 0.5 and i + 1 < n:
                m[i] = max(m[i - 1], m[i + 1])
        self.mot = m

    def _switch(self, i):
        """Vrai si la zone des mains change pour de bon à la frame i (arme rangée / couteau sorti)."""
        n, F = self.n, self.F
        if i < 10 or i + 8 >= n or self.chg[i] < 0.45:
            return False
        before = F[max(0, i - 12):i - 2].mean(axis=0)
        before /= np.linalg.norm(before) + 1e-6
        after = F[i + 3:min(n, i + 20)] @ before
        return float(np.median(after)) < 0.55

    def _knife_start(self, s):
        """Depuis le début du changement : saute les frames vides (mains vides) et garde la 1re frame
        où le couteau apparaît (la plus forte montée du changement au début)."""
        n, c = self.n, self.chg
        j = s
        gap = [k for k in range(s + 1, min(n, s + 5)) if c[k] < 0.5]
        if gap:                                      # arme rangée puis mains vides : on attend le couteau
            nxt = [k for k in range(gap[0], min(n, gap[0] + 12)) if c[k] >= 0.5]
            if nxt:
                j = nxt[0]
        best, bj = 0.0, j
        for k in range(j, min(n, j + 4)):
            d = c[k] - c[k - 1]
            if d > best + 0.05:
                best, bj = d, k
        return bj if best >= 0.2 else j

    def _flicks(self):
        """Pics de mouvement de toute l'image (flick away), dans l'ordre."""
        m, n = self.mot, self.n
        med = float(np.median(m[m > 0])) if np.any(m > 0) else 0.0
        thr = max(22.0, 3.0 * med)
        return [i for i in range(1, n - 1) if m[i] >= thr and m[i] >= m[i - 1] and m[i] >= m[i + 1]]

    def _drop(self, s):
        """Combien l'arme disparaît au changement s (petit = l'arme a vraiment été rangée)."""
        F = self.F
        g = F[max(0, s - 25):max(1, s - 3)].mean(axis=0)
        g /= np.linalg.norm(g) + 1e-6
        pre = float(np.mean(F[max(0, s - 25):max(1, s - 3)] @ g))
        post = float(np.mean(F[s + 3:min(self.n, s + 25)] @ g))
        return post / max(pre, 1e-3)

    def keyframes(self, kill_index=None):
        """(début, fin) en secondes.

        On part du flick away (gros mouvement de toute l'image) qui suit le kill, on recule jusqu'au
        changement arme -> couteau juste avant (celui où l'arme disparaît le plus), puis on avance à la
        1re frame du couteau. Keyframe 2 = flick + 20 frames."""
        n = self.n
        cands = [i for i in range(10, n - 8) if self._switch(i)]
        starts = [i for k, i in enumerate(cands) if k == 0 or i - cands[k - 1] > 6]
        flicks = self._flicks()
        lo = 0
        if kill_index is not None and self.kills:
            lo = self.kills[kill_index] - FPS // 2              # la bannière choisie : on recule un peu
        s = flick = None
        for f in flicks:
            if f < lo:
                continue
            win = [i for i in starts if f - int(1.3 * FPS) <= i <= f + 2 and i >= lo - FPS // 2]
            if win:
                s = min(win, key=self._drop)
                flick = f
                break
        if s is None:                                           # pas de flick net : le changement le plus fort
            pool = [i for i in starts if i >= lo] or starts
            s = min(pool, key=self._drop) if pool else int(np.argmax(self.chg))
        start = min(self._knife_start(s), n - 2)
        if flick is None or flick < start - 3:
            later = [f for f in flicks if f >= start - 3]
            flick = later[0] if later else None

        duree = self.knife.get("duree")
        if flick is not None:
            end = flick + FLICK_FRAMES
        elif duree:
            end = start + int(round(duree * FPS))
        else:
            end = start + FLICK_FRAMES + FPS // 6
        end = min(max(end, start + 1), n - 1)
        self.flick = flick
        return start / FPS, end / FPS


def detect(path, knife=None):
    a = Analysis(path, knife)
    s, e = a.keyframes()
    return s, e, a.length


def grab_png(path, t, width=480):
    """Image PNG (octets) de la vidéo à l'instant t, pour l'aperçu."""
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                        *vclip.input_args(path, ss=t), "-frames:v", "1", "-vf", f"scale={width}:-2",
                        "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True, creationflags=audio._NO_WINDOW)
    return p.stdout


def save_knife_image(name, path, t):
    """Garde la frame « couteau sorti » comme image de référence du couteau."""
    target = knife_dir() / (re.sub(r'[<>:"/\\|?*]', "_", name) + ".png")
    subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                    *vclip.input_args(path, ss=t), "-frames:v", "1", str(target)],
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
    out = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-i", vclip.source(path)], capture_output=True,
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
                                *vclip.input_args(path, ss=lo + s0 / sfps), "-t", f"{(m1 + PAD - s0) / sfps:.6f}",
                                "-an", "-vf", vf,
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
    from . import fit
    vf += f",{fit.mirror_fill(path, W, H)},setsar=1"                # bords en miroir, pas de barres noires
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

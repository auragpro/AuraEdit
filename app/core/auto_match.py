"""Edit auto : on regarde chaque plan de l'edit fini et on reconnaît ce que c'est, en le comparant à tes clips.

Deux étapes :
1. la CATÉGORIE (flick couteau, kunai, dash, dash back, dismiss) : surtout la FORME de ce qu'on a en main
   (contours du bas de l'image, gauche et droite séparés), peu la couleur ;
2. dans les flicks, QUEL couteau : là la couleur du skin compte beaucoup.

Pour les couteaux on apprend sur les images où le couteau est sorti (début du time remap, image de
référence du couteau), pas sur les moments où le joueur tient encore son arme.
"""
import subprocess
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import audio, vclip

SW, SH = 160, 90
EDIT_FPS = 10
CLIP_FPS = 6
FLICK = "Flick"


def _frames(path, fps=CLIP_FPS, file=False):
    args = ["-i", str(path)] if file else vclip.input_args(path)
    vf = f"scale={SW}:{SH},format=rgb24" if file else f"fps={fps},scale={SW}:{SH},format=rgb24"
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *args, "-an", "-vf", vf,
                        "-f", "rawvideo", "-"], capture_output=True, creationflags=audio._NO_WINDOW)
    n = len(p.stdout) // (SW * SH * 3)
    return np.frombuffer(p.stdout[:n * SW * SH * 3], np.uint8).reshape(n, SH, SW, 3)


HUD = "crop=iw*0.12:ih*0.13:iw*0.44:ih*0.86,scale=32:32,format=gray"     # icône d'arme au centre du HUD


def _hud(path, fps=CLIP_FPS):
    """Le centre du HUD en bas de l'image (là où l'icône du kunai s'affiche), image par image."""
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *vclip.input_args(path), "-an",
                        "-vf", f"fps={fps},{HUD}", "-f", "rawvideo", "-"], capture_output=True,
                       creationflags=audio._NO_WINDOW)
    n = len(p.stdout) // 1024
    a = np.frombuffer(p.stdout[:n * 1024], np.uint8).reshape(n, 1024).astype(np.float32)
    a -= a.mean(axis=1, keepdims=True)
    a /= np.linalg.norm(a, axis=1, keepdims=True) + 1e-6
    return a


def _hue_sat(img):
    f = img.astype(np.float32) / 255
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    mx, mn = f.max(axis=2), f.min(axis=2)
    d = mx - mn + 1e-6
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 30
    s = np.where(mx > 0, (mx - mn) / (mx + 1e-6), 0)
    return h, s


Y0 = int(SH * 0.4)          # on regarde le bas de l'image (arme, couteau, main)


def desc(img):
    """(forme, couleur) du bas de l'image."""
    g = img.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    gy, gx = np.gradient(g)
    mag = np.hypot(gx, gy)[Y0:]
    ang = (np.arctan2(gy, gx) % np.pi)[Y0:]
    b = np.minimum((ang / np.pi * 8).astype(int), 7)
    cells = []
    for rows in np.array_split(np.arange(mag.shape[0]), 3):
        for cols in np.array_split(np.arange(SW), 6):
            m = mag[np.ix_(rows, cols)].ravel()
            cells.append(np.bincount(b[np.ix_(rows, cols)].ravel(), weights=m, minlength=8))
    hog = np.sqrt(np.concatenate(cells))
    hog /= np.linalg.norm(hog) + 1e-6
    hue, sat = _hue_sat(img)
    cols = []
    for x0, x1 in ((0, SW // 2), (SW // 2, SW)):
        h, _, _ = np.histogram2d(hue[Y0:, x0:x1].ravel(), sat[Y0:, x0:x1].ravel(), bins=[18, 4],
                                 range=[[0, 180], [0, 1.0001]])
        h = h.ravel().astype(np.float32)
        cols.append(h / (h.sum() + 1e-6))
    return hog.astype(np.float32), np.concatenate(cols)


def s_form(a, b):
    return float(np.dot(a[0], b[0]))


def s_color(a, b):
    return float(np.minimum(a[1], b[1]).sum() / 2)


def _ref_times(clip, rm, special, n):
    """Indices des images à apprendre dans un clip décodé à CLIP_FPS."""
    if n == 0:
        return []
    if rm and not special:
        a, b = float(rm["debut"]), float(rm["fin"])
        ts = [a, a + 0.1, a + 0.2, a + 0.35, max(a, b - 0.1)]
        return sorted({min(n - 1, max(0, int(t * CLIP_FPS))) for t in ts})
    lo, hi = (0.1, 0.9) if special else (0.35, 0.97)            # couteau sans time remap : plutôt la fin
    return sorted({min(n - 1, int(n * (lo + (hi - lo) * k / 9))) for k in range(10)})


def analyse(edit, bounds, classes, remaps, progress=None, cancelled=None):
    """classes : {clé: {"clips", "image", "pool", "special"}}.
    Renvoie, pour chaque plan, les clés triées : d'abord celles de la bonne catégorie (la meilleure en tête)."""
    refs = {k: [] for k in classes}
    for key, c in classes.items():
        if c.get("image"):
            f = _frames(c["image"], file=True)
            if len(f):
                refs[key] += [desc(f[0])] * 2           # l'image de référence du couteau compte double
    # icône du kunai au centre du HUD : apprise sur tes clips kunai, comparée aux autres clips
    hud_k, hud_o = [], []
    kunai_keys = [k for k, c in classes.items() if c["special"] and c["pool"].lower().startswith("kunai")]
    try:
        for key, c in classes.items():
            for clip in c["clips"][:6]:
                h = _hud(clip)
                if len(h):
                    pick = h[np.linspace(0, len(h) - 1, min(6, len(h))).astype(int)]
                    (hud_k if key in kunai_keys else hud_o).extend(pick)
    except Exception:                               # noqa: BLE001
        hud_k, hud_o = [], []
    jobs = [(key, clip) for key, c in classes.items() for clip in c["clips"][:16]]     # plus d'exemples appris
    done = 0
    with ThreadPoolExecutor(6) as ex:
        futs = [(key, clip, ex.submit(_frames, clip)) for key, clip in jobs]
        for key, clip, f in futs:
            fr = f.result()
            for i in _ref_times(clip, remaps.get(clip), classes[key]["special"], len(fr)):
                refs[key].append(desc(fr[i]))
            done += 1
            if progress:
                progress(0.8 * done / max(1, len(futs)), "J'apprends tes clips...")
            if cancelled and cancelled():
                raise InterruptedError()
    if progress:
        progress(0.8, "Je regarde l'edit...")
    frames = _frames(edit, EDIT_FPS)
    try:
        ehud = _hud(edit, EDIT_FPS) if hud_k and hud_o else []
    except Exception:                               # noqa: BLE001
        ehud = []
    HK = np.array(hud_k) if len(hud_k) else None
    HO = np.array(hud_o) if len(hud_o) else None
    cat = {k: (c["pool"] if c["special"] else FLICK) for k, c in classes.items()}
    out = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        idx = sorted({min(len(frames) - 1, max(0, int((a + (b - a) * f) * EDIT_FPS)))
                      for f in (0.2, 0.35, 0.5, 0.65, 0.8)}) if len(frames) else []
        ds = [desc(frames[j]) for j in idx]
        form, kn = {}, {}
        for key, rl in refs.items():
            if not rl or not ds:
                form[key] = kn[key] = -1.0
                continue
            # pour chaque image du plan : la meilleure ressemblance ; puis la moyenne sur le plan
            form[key] = float(np.mean([max(0.8 * s_form(d, r) + 0.2 * s_color(d, r) for r in rl) for d in ds]))
            kn[key] = float(np.mean([max(0.4 * s_form(d, r) + 0.6 * s_color(d, r) for r in rl) for d in ds]))
        # catégorie : vote des images les plus ressemblantes (k plus proches voisins) sur chaque image du plan,
        # plus solide qu'un seul maximum (un kunai ne « vole » plus un flick sur une image isolée)
        cats = {}
        for d in ds:
            sc = sorted(((0.8 * s_form(d, r) + 0.2 * s_color(d, r), key) for key, rl in refs.items() for r in rl),
                        reverse=True)[:7]
            for rank, (v, key) in enumerate(sc):
                cats[cat[key]] = cats.get(cat[key], 0.0) + v * (1.0 - rank * 0.1)
        for key, v in form.items():                     # + la meilleure ressemblance moyenne (départage)
            cats[cat[key]] = cats.get(cat[key], 0.0) + 0.5 * max(0.0, v)
        best = max(cats, key=cats.get) if cats else None
        # le kunai d'abord : l'icône du kunai est-elle au centre du HUD ?
        if HK is not None and HO is not None and len(ehud) and kunai_keys:
            hk, ho = [], []
            for j in idx:
                if j < len(ehud):
                    hk.append(float((HK @ ehud[j]).max()))
                    ho.append(float((HO @ ehud[j]).max()))
            if hk:
                kunai_seen = np.mean(hk) > np.mean(ho) + 0.03 and np.mean(hk) > 0.55
                kcat = cat[kunai_keys[0]]
                if kunai_seen:
                    best = kcat                         # kunai vu : on garde le kunai (le bras se choisit après)
                elif best == kcat:                      # pas de kunai : est-ce un dash ? sinon la catégorie suivante
                    rest = {c: v for c, v in cats.items() if c != kcat}
                    best = max(rest, key=rest.get) if rest else best
        inside = [k for k in classes if cat[k] == best]
        inside.sort(key=lambda k: -(kn[k] if best == FLICK else form[k]))
        others = sorted([k for k in classes if cat[k] != best], key=lambda k: -form[k])
        out.append(inside + others)
    if progress:
        progress(1.0, "Terminé")
    return out


# ---------------------------------------------------------------- caler le début sur l'edit
AW, AH = 96, 54


def _gray(path, ss=None, dur=None, fps=60):
    args = vclip.input_args(path, ss=ss) if ss is not None else vclip.input_args(path)
    if dur is not None:
        args = [*args, "-t", f"{dur:.3f}"]
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *args, "-an", "-vf",
                        f"fps={fps},scale={AW}:{AH},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, creationflags=audio._NO_WINDOW)
    n = len(p.stdout) // (AW * AH)
    a = np.frombuffer(p.stdout[:n * AW * AH], np.uint8).reshape(n, AW * AH).astype(np.float32)
    a -= a.mean(axis=1, keepdims=True)
    a /= np.linalg.norm(a, axis=1, keepdims=True) + 1e-6
    return a


def _flick_onset(clip):
    """1re frame du flick away (le début du gros mouvement de toute l'image), en secondes, ou None."""
    from . import timeremap as tr
    try:
        a = tr.Analysis(clip)
    except Exception:                       # noqa: BLE001
        return None
    fl = a._flicks()
    if a.kills:                             # le flick qui suit la bannière de kill
        after = [f for f in fl if f >= a.kills[0] - tr.FPS // 2]
        fl = after or fl
    if not fl:
        try:
            return a.keyframes()[0]
        except Exception:                   # noqa: BLE001
            return None
    f = fl[0]
    thr = 0.3 * a.mot[f]
    j = f
    while j > 1 and a.mot[j - 1] > thr:
        j -= 1
    return j / tr.FPS


def align_start(edit, t, clip, same=0.8):
    """Où commencer le clip pour copier la 1re frame du plan de l'edit (instant t).
    Même cut retrouvé dans le clip -> (instant, True). Sinon -> (1re frame du flick away, False)."""
    ref = _gray(edit, ss=max(0.0, t + 2 / 60), dur=0.05)
    cf = _gray(clip)
    if len(ref) and len(cf):
        sc = cf @ ref[0]
        i = int(np.argmax(sc))
        if float(sc[i]) >= same:
            return i / 60.0, True
    return _flick_onset(clip), False

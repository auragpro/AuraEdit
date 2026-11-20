"""Incrustation d'une vidéo par-dessus un clip, avec suppression du fond (fond vert ou n'importe quelle couleur).

Inspiré de Keylight + Advanced Spill Suppressor d'After Effects :
- le masque se calcule par « différence de couleur » : on mesure à quel point chaque pixel va dans la
  direction de la couleur du fond (et pas seulement s'il lui ressemble), donc les ombres et les plis
  du fond partent aussi, et les couleurs proches (jaune, peau...) restent ;
- douceur, rétrécissement et adoucissement des bords pour un contour propre ;
- suppression du débordement : on retire la teinte du fond qui bave sur le sujet, en gardant la luminosité.
"""
import subprocess

import numpy as np

from . import audio

DEFAULT = {"fichier": None, "couleur": "#00ff00", "tolerance": 50, "douceur": 30, "retrecir": 1,
           "adoucir": 1, "spill": 80, "taille": 100, "x": 0, "y": 0, "debut": 0.0, "boucle": False}
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


def cfg_full(cfg):
    return {**DEFAULT, **(cfg or {})}


def hex_rgb(h):
    h = str(h).lstrip("#")
    try:
        return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255
    except ValueError:
        return np.array([0, 1, 0], np.float32)


def rgb_hex(c):
    return "#" + "".join(f"{int(max(0, min(255, round(v)))):02x}" for v in c)


def _erode(a, r):
    """Rétrécit le masque de r pixels (minimum glissant, sans OpenCV)."""
    for ax in (0, 1):
        p = np.pad(a, [(r, r) if i == ax else (0, 0) for i in (0, 1)], mode="edge")
        n = a.shape[ax]
        out = p.take(range(0, n), axis=ax)
        for k in range(1, 2 * r + 1):
            out = np.minimum(out, p.take(range(k, k + n), axis=ax))
        a = out
    return a


def _box(a, r):
    for ax in (0, 1):
        p = np.pad(a, [(r + 1, r) if i == ax else (0, 0) for i in (0, 1)], mode="edge")
        c = np.cumsum(p, axis=ax, dtype=np.float32)
        n = a.shape[ax]
        a = (c.take(range(2 * r + 1, 2 * r + 1 + n), axis=ax) - c.take(range(0, n), axis=ax)) / (2 * r + 1)
    return a


def _blur(a, sigma):
    """Flou ~gaussien (3 flous boîte), sans OpenCV."""
    r = max(1, int(round(sigma * 0.9)))
    for _ in range(3):
        a = _box(a, r)
    return a.astype(np.float32)


def _match(P, C):
    """1 = exactement la couleur du fond, <= 0 = rien à voir."""
    kv = C - C.mean()
    n2 = float((kv ** 2).sum())
    if n2 < 0.004:                                  # fond gris / blanc / noir : simple distance
        return 1 - np.linalg.norm(P - C, axis=2) * 2.5, None, None
    dev = P - P.mean(axis=2, keepdims=True)
    s = (dev @ kv) / n2
    res = np.linalg.norm(dev - s[..., None] * kv, axis=2) / np.sqrt(n2)
    # la luminosité compte un peu (un fond vert foncé reste du fond, mais pas un objet noir)
    return s - res, s, kv


def key(img, cfg, scale=1.0):
    """img : HxWx3 uint8 RGB. Renvoie (rgb float32 0..1 nettoyé, alpha float32 0..1)."""
    cfg = cfg_full(cfg)
    P = img.astype(np.float32) / 255
    C = hex_rgb(cfg["couleur"])
    m, s, kv = _match(P, C)
    hi = 1 - float(cfg["tolerance"]) * 0.008
    lo = hi - max(0.02, float(cfg["douceur"]) * 0.008)
    a = np.clip((hi - m) / (hi - lo), 0, 1).astype(np.float32)
    r = int(round(float(cfg["retrecir"]) * scale))
    if r > 0:
        a = _erode(a, r)
    b = float(cfg["adoucir"]) * scale
    if b > 0.3:
        a = _blur(a, b)
    amt = float(cfg["spill"]) / 100
    if amt > 0 and kv is not None:
        y0 = P @ LUMA
        P = P - (amt * np.clip(s, 0, None))[..., None] * kv
        P = P + (y0 - P @ LUMA)[..., None]            # garde la luminosité
        P = np.clip(P, 0, 1)
    return P, a


def matte_frame(img, cfg, scale=1.0):
    """Vue « masque » noir/blanc, comme l'affichage Screen Matte de Keylight."""
    _, a = key(img, cfg, scale)
    return np.repeat((a * 255).astype(np.uint8)[..., None], 3, axis=2)


def layout(cfg, W, H):
    """Taille du calque incrusté et sa position (coin haut-gauche) dans une image WxH."""
    cfg = cfg_full(cfg)
    sc = max(0.05, float(cfg["taille"]) / 100)
    w, h = max(2, int(W * sc) // 2 * 2), max(2, int(H * sc) // 2 * 2)
    x = (W - w) // 2 + int(float(cfg["x"]) / 100 * W)
    y = (H - h) // 2 + int(float(cfg["y"]) / 100 * H)
    return w, h, x, y


def fit_filter(cfg, w, h):
    """Filtre ffmpeg qui met la vidéo dans w x h ; les bandes ajoutées ont la couleur du fond (donc enlevées)."""
    col = cfg_full(cfg)["couleur"].lstrip("#")
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x{col},setsar=1,format=rgb24")


def composite(bg, fg, cfg, x, y, scale=1.0, view="resultat"):
    """Pose fg (détouré) sur bg (uint8 RGB) à la position x, y. Renvoie un uint8 RGB."""
    H, W = bg.shape[:2]
    h, w = fg.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    out = bg.copy()
    if x1 <= x0 or y1 <= y0:
        return out
    if view == "brut":
        out[y0:y1, x0:x1] = fg[y0 - y:y1 - y, x0 - x:x1 - x]
        return out
    rgb, a = key(fg, cfg, scale)
    rgb, a = rgb[y0 - y:y1 - y, x0 - x:x1 - x], a[y0 - y:y1 - y, x0 - x:x1 - x, None]
    if view == "masque":
        out[:] = 0
        out[y0:y1, x0:x1] = np.repeat((a * 255).astype(np.uint8), 3, axis=2)
        return out
    zone = out[y0:y1, x0:x1].astype(np.float32) / 255
    out[y0:y1, x0:x1] = ((zone * (1 - a) + rgb * a) * 255 + 0.5).astype(np.uint8)
    return out


def read_frame(path, t, w, h, vf):
    p = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, t):.3f}",
                        "-i", str(path), "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, creationflags=audio._NO_WINDOW)
    if len(p.stdout) < w * h * 3:
        return None
    return np.frombuffer(p.stdout[:w * h * 3], np.uint8).reshape(h, w, 3)


def border_color(img):
    """Couleur la plus probable du fond : médiane des bords de l'image."""
    e = np.concatenate([img[:4].reshape(-1, 3), img[-4:].reshape(-1, 3),
                        img[:, :4].reshape(-1, 3), img[:, -4:].reshape(-1, 3)])
    return rgb_hex(np.median(e, axis=0))


def apply(part, out, cfg, W, H, FPS, is_cancelled=None, progress=None, total=0):
    """Incruste la vidéo de cfg["fichier"] sur le clip déjà préparé `part` (W x H, FPS) -> `out`."""
    cfg = cfg_full(cfg)
    ff = audio.ffmpeg_exe()
    w, h, x, y = layout(cfg, W, H)
    nw = audio._NO_WINDOW
    bg = subprocess.Popen([ff, "-hide_banner", "-loglevel", "error", "-i", str(part), "-f", "rawvideo",
                           "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          creationflags=nw)
    loop = ["-stream_loop", "-1"] if cfg["boucle"] else []
    fg = subprocess.Popen([ff, "-hide_banner", "-loglevel", "error", *loop, "-ss", f"{float(cfg['debut']):.3f}",
                           "-i", str(cfg["fichier"]), "-an", "-vf", f"fps={FPS}," + fit_filter(cfg, w, h),
                           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, creationflags=nw)
    enc = subprocess.Popen([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "10", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE,
                           stderr=subprocess.PIPE, creationflags=nw)
    nb, nf = W * H * 3, w * h * 3
    fg_on, i = True, 0
    try:
        while True:
            raw = bg.stdout.read(nb)
            if len(raw) < nb:
                break
            frame = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
            if fg_on:
                rf = fg.stdout.read(nf)
                if len(rf) < nf:
                    fg_on = False
                else:
                    frame = composite(frame, np.frombuffer(rf, np.uint8).reshape(h, w, 3), cfg, x, y)
            enc.stdin.write(frame.tobytes())
            i += 1
            if is_cancelled and is_cancelled():
                raise InterruptedError()
            if progress and total and i % 15 == 0:
                progress(min(1.0, i / total))
    finally:
        for p in (bg, fg):
            p.kill()
        try:
            enc.stdin.close()
        except OSError:
            pass
        err = enc.stderr.read()
        enc.wait()
        for p in (bg, fg):
            p.wait()
    if enc.returncode != 0:
        raise RuntimeError(err.decode("utf-8", "replace")[-600:])

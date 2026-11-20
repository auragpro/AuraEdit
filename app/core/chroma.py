"""Incrustation d'une vidéo par-dessus l'edit, avec suppression du fond (fond vert ou n'importe quelle couleur).

Inspiré de Keylight + Advanced Spill Suppressor d'After Effects :
- le masque se calcule par « différence de couleur » : on mesure à quel point chaque pixel va dans la
  direction de la couleur du fond, donc les ombres et les plis du fond partent aussi, et les couleurs
  proches (jaune, peau...) restent ;
- bords propres : on « dé-mélange » la couleur du fond des pixels de bord (plus de liseré vert/noir),
  puis rétrécir / adoucir le masque ;
- suppression du débordement : on retire la teinte du fond qui bave sur le sujet, en gardant la luminosité.

La vidéo incrustée commence sur un clip et peut continuer sur les clips suivants. Elle peut apparaître
et disparaître en fondu ou en « Dissolve Luma » (désintégration selon la luminosité, façon S_DissolveLuma).
Si elle est en 30 i/s, elle est fluidifiée en 60 i/s par interpolation de mouvement.
"""
import subprocess

import numpy as np

from . import audio

DEFAULT = {"fichier": None, "couleur": "#00ff00", "tolerance": 50, "douceur": 30, "retrecir": 1,
           "adoucir": 1, "spill": 80, "taille": 100, "x": 0, "y": 0, "debut": 0.0, "fin": None,
           "boucle": False, "continuer": True, "fluide": True,
           "entree": "aucune", "entree_duree": 0.3, "sortie": "aucune", "sortie_duree": 0.3}
TRANSITIONS = [("aucune", "Aucune"), ("fondu", "Fondu"), ("dissolve", "Dissolve Luma (désintégration)")]
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


# ------------------------------------------------------------------ outils masque (sans OpenCV)
def _erode(a, r):
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
    r = max(1, int(round(sigma * 0.9)))
    for _ in range(3):
        a = _box(a, r)
    return a.astype(np.float32)


# ------------------------------------------------------------------ détourage
def _match(P, C):
    """1 = exactement la couleur du fond, <= 0 = rien à voir."""
    kv = C - C.mean()
    n2 = float((kv ** 2).sum())
    if n2 < 0.004:                                  # fond gris / blanc / noir : simple distance
        return 1 - np.linalg.norm(P - C, axis=2) * 2.5, None, None
    dev = P - P.mean(axis=2, keepdims=True)
    s = (dev @ kv) / n2
    res = np.linalg.norm(dev - s[..., None] * kv, axis=2) / np.sqrt(n2)
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
    # bords : on enlève la part de couleur du fond mélangée dans les pixels semi-transparents
    edge = (a > 0.02) & (a < 0.98)
    if edge.any():
        ae = a[edge][:, None]
        P[edge] = np.clip((P[edge] - (1 - ae) * C) / ae, 0, 1)
    r = int(round(float(cfg["retrecir"]) * scale))
    if r > 0:
        a = _erode(a, r)
    b = float(cfg["adoucir"]) * scale
    if b > 0.3:
        a = _blur(a, b)
    amt = float(cfg["spill"]) / 100
    if amt > 0 and kv is not None:
        dev = P - P.mean(axis=2, keepdims=True)
        s2 = np.clip((dev @ kv) / float((kv ** 2).sum()), 0, None)
        y0 = P @ LUMA
        P = P - (amt * s2)[..., None] * kv
        P = np.clip(P + (y0 - P @ LUMA)[..., None], 0, 1)            # garde la luminosité
    return P, a


def layout(cfg, W, H):
    """Taille du calque incrusté et sa position (coin haut-gauche) dans une image WxH."""
    cfg = cfg_full(cfg)
    sc = max(0.05, float(cfg["taille"]) / 100)
    w, h = max(2, int(W * sc) // 2 * 2), max(2, int(H * sc) // 2 * 2)
    x = (W - w) // 2 + int(float(cfg["x"]) / 100 * W)
    y = (H - h) // 2 + int(float(cfg["y"]) / 100 * H)
    return w, h, x, y


def fit_filter(cfg, w, h, motion=None):
    """Met la vidéo dans w x h (bandes de la couleur du fond, donc enlevées). motion : filtre de cadence."""
    col = cfg_full(cfg)["couleur"].lstrip("#")
    f = (f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=bicubic,"
         f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x{col},setsar=1")
    return f + (f",{motion}" if motion else "") + ",format=rgb24"


# ------------------------------------------------------------------ transitions
def _noise(h, w, seed=7):
    rng = np.random.default_rng(seed)
    n = rng.random((max(2, h // 12 + 2), max(2, w // 12 + 2))).astype(np.float32)
    n = np.repeat(np.repeat(n, 12, axis=0), 12, axis=1)[:h, :w]
    return _blur(n, 6)


def visibility(cfg, t, span, fg=None, noise=None):
    """Multiplicateur d'opacité à l'instant t (s) dans la vidéo incrustée qui dure span s.
    Renvoie (scalaire ou tableau HxW, bord lumineux ou None)."""
    cfg = cfg_full(cfg)
    phases = []
    di, do = float(cfg["entree_duree"]), float(cfg["sortie_duree"])
    if cfg["entree"] != "aucune" and di > 0 and t < di:
        phases.append((cfg["entree"], max(0.0, t / di)))
    if cfg["sortie"] != "aucune" and do > 0 and t > span - do:
        phases.append((cfg["sortie"], max(0.0, (span - t) / do)))
    mult, glow = 1.0, None
    for kind, p in phases:
        p = min(1.0, p)
        if kind == "fondu":
            mult = mult * p
        elif kind == "dissolve" and fg is not None:
            d = 0.6 * (fg.astype(np.float32) / 255 @ LUMA) + 0.4 * (noise if noise is not None else 0.5)
            soft = 0.12
            m = np.clip((p * (1 + soft) - (1 - d)) / soft, 0, 1)        # les zones claires partent en dernier
            g = np.clip(1 - np.abs(m * 2 - 1), 0, 1) * (m < 1)
            mult = mult * m
            glow = g if glow is None else np.maximum(glow, g)
    return mult, glow


def composite(bg, fg, cfg, x, y, scale=1.0, view="resultat", mult=1.0, glow=None):
    """Pose fg (détouré) sur bg (uint8 RGB) à la position x, y. Renvoie un uint8 RGB."""
    H, W = bg.shape[:2]
    h, w = fg.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    out = bg.copy()
    if x1 <= x0 or y1 <= y0:
        return out
    cut = (slice(y0 - y, y1 - y), slice(x0 - x, x1 - x))
    if view == "brut":
        out[y0:y1, x0:x1] = fg[cut]
        return out
    rgb, a = key(fg, cfg, scale)
    a = a * mult if np.isscalar(mult) else a * mult
    if glow is not None:
        rgb = np.clip(rgb + (glow * 0.9)[..., None] * (a > 0.01)[..., None], 0, 1)
    rgb, a = rgb[cut], a[cut][..., None]
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


# ------------------------------------------------------------------ rendu sur toute la vidéo
class _Layer:
    def __init__(self, item, W, H, FPS):
        from . import render, timeremap
        self.cfg = cfg_full(item)
        f = self.cfg["fichier"]
        total = render.duration(f)
        a = float(self.cfg["debut"])
        b = float(self.cfg["fin"]) if self.cfg["fin"] else total
        b = min(b, total) if total else b
        part = max(0.05, b - a)
        if self.cfg["continuer"]:
            self.span = part
        else:
            self.span = float(item["clip_duree"]) if self.cfg["boucle"] else min(part, float(item["clip_duree"]))
        self.f0 = int(round(float(item["t0"]) * FPS))
        self.n = max(1, int(round(self.span * FPS)))
        self.FPS = FPS
        self.w, self.h, self.x, self.y = layout(self.cfg, W, H)
        src = timeremap.source_fps(f) or FPS
        motion = (f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
                  if self.cfg["fluide"] and src < FPS - 1 else f"fps={FPS}")
        loop = ["-stream_loop", "-1"] if self.cfg["boucle"] and not self.cfg["continuer"] else []
        dur = [] if loop else ["-t", f"{part:.3f}"]
        self.cmd = [audio.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *loop, "-ss", f"{a:.3f}", *dur,
                    "-i", str(f), "-an", "-vf", fit_filter(self.cfg, self.w, self.h, motion),
                    "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc, self.k, self.done = None, 0, False
        self.noise = _noise(self.h, self.w) if "dissolve" in (self.cfg["entree"], self.cfg["sortie"]) else None

    def frame(self, fi, img):
        if self.done or fi < self.f0:
            return img
        if self.k >= self.n:
            self.close()
            return img
        if self.proc is None:
            self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         creationflags=audio._NO_WINDOW)
        raw = self.proc.stdout.read(self.w * self.h * 3)
        if len(raw) < self.w * self.h * 3:
            self.close()
            return img
        fg = np.frombuffer(raw, np.uint8).reshape(self.h, self.w, 3)
        mult, glow = visibility(self.cfg, self.k / self.FPS, self.span, fg, self.noise)
        self.k += 1
        return composite(img, fg, self.cfg, self.x, self.y, mult=mult, glow=glow)

    def close(self):
        self.done = True
        if self.proc is not None:
            self.proc.kill()
            self.proc.wait()
            self.proc = None


def apply_timeline(src, out, items, W, H, FPS, total=0, is_cancelled=None, progress=None):
    """Incruste toutes les vidéos `items` ({réglages..., "t0", "clip_duree"}) sur la vidéo src -> out."""
    ff = audio.ffmpeg_exe()
    nw = audio._NO_WINDOW
    layers = [_Layer(it, W, H, FPS) for it in items]
    bg = subprocess.Popen([ff, "-hide_banner", "-loglevel", "error", "-i", str(src), "-f", "rawvideo",
                           "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          creationflags=nw)
    enc = subprocess.Popen([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "10", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE,
                           stderr=subprocess.PIPE, creationflags=nw)
    nb, i = W * H * 3, 0
    try:
        while True:
            raw = bg.stdout.read(nb)
            if len(raw) < nb:
                break
            frame = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
            for L in layers:
                frame = L.frame(i, frame)
            enc.stdin.write(np.ascontiguousarray(frame).tobytes())
            i += 1
            if is_cancelled and is_cancelled():
                raise InterruptedError()
            if progress and total and i % 15 == 0:
                progress(min(1.0, i / total))
    finally:
        for L in layers:
            L.close()
        bg.kill()
        try:
            enc.stdin.close()
        except OSError:
            pass
        err = enc.stderr.read()
        enc.wait()
        bg.wait()
    if enc.returncode != 0:
        raise RuntimeError(err.decode("utf-8", "replace")[-600:])

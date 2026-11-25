"""Textes de l'edit : police du PC, effet « Biseautage et estampage » et mode de fusion « Incrustation »
(comme Photoshop / After Effects : le texte devient transparent, on ne voit que son relief sur la vidéo)."""
import numpy as np

DEFAULT = {"texte": "TEXTE", "police": "Arial", "taille": 260, "gras": True, "x": 0, "y": 0,
           "biseau": True, "biseau_taille": 10, "biseau_force": 70, "mode": "incrustation",
           "couleur": "#ffffff", "remplissage": 8, "debut": 0, "fin": 0}
MODES = [("incrustation", "Incrustation (texte transparent)"), ("normal", "Normal (texte plein)")]


def full(cfg):
    return {**DEFAULT, **(cfg or {})}


def _mask(cfg, W, H, scale=1.0):
    """Masque du texte (0..1) dessiné avec la police du PC."""
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QImage, QPainter
    img = QImage(W, H, QImage.Format.Format_Grayscale8)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    f = QFont(cfg["police"])
    f.setPixelSize(max(4, int(cfg["taille"] * scale)))
    f.setBold(bool(cfg["gras"]))
    p.setFont(f)
    p.setPen(QColor(255, 255, 255))
    dx, dy = float(cfg["x"]) / 100 * W, float(cfg["y"]) / 100 * H
    p.drawText(QRectF(dx, dy, W, H), int(Qt.AlignmentFlag.AlignCenter), str(cfg["texte"]))
    p.end()
    ptr = img.constBits()
    ptr.setsize(img.bytesPerLine() * H)
    a = np.frombuffer(ptr, np.uint8).reshape(H, img.bytesPerLine())[:, :W]
    return a.astype(np.float32) / 255


def _blur(a, r):
    r = int(max(1, r))
    for axis in (0, 1):
        for _ in range(2):
            c = np.cumsum(np.pad(a, [(r + 1, r) if ax == axis else (0, 0) for ax in range(2)], mode="edge"),
                          axis=axis)
            if axis == 0:
                a = (c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)
            else:
                a = (c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)
    return a


def _bevel(mask, size, force):
    """Relief intérieur (biseautage) éclairé en haut à gauche : >0 = lumière, <0 = ombre."""
    h = _blur(mask, size)
    gy, gx = np.gradient(h)
    shade = -(gx * -0.7071 + gy * -0.7071)            # lumière venant du haut à gauche
    shade = shade * mask * (float(size) * 2.2) * (force / 50.0)
    return np.clip(shade, -1, 1)


def layer(cfg, W, H, scale=1.0):
    """Calque prêt à poser. Incrustation : image grise (0,5 = aucun changement), sinon RGBA."""
    cfg = full(cfg)
    m = _mask(cfg, W, H, scale)
    sh = _bevel(m, max(1, cfg["biseau_taille"] * scale), cfg["biseau_force"]) if cfg["biseau"] else 0 * m
    if cfg["mode"] == "incrustation":
        g = 0.5 + 0.5 * sh + m * float(cfg["remplissage"]) / 200.0
        g = np.clip(g, 0, 1)
        return (np.repeat(g[..., None], 3, axis=2) * 255 + 0.5).astype(np.uint8)
    col = np.array([int(cfg["couleur"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255
    rgb = np.clip(col[None, None, :] + 0.6 * sh[..., None], 0, 1)
    return np.dstack([rgb * 255, m * 255]).astype(np.uint8)


def blend(base, lay, mode):
    """Aperçu : pose le calque sur une image (uint8 RGB)."""
    b = base.astype(np.float32) / 255
    if mode == "incrustation":
        l = lay.astype(np.float32) / 255
        out = np.where(b < 0.5, 2 * b * l, 1 - 2 * (1 - b) * (1 - l))
    else:
        a = lay[..., 3:4].astype(np.float32) / 255
        out = b * (1 - a) + lay[..., :3].astype(np.float32) / 255 * a
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


def save_png(arr, path):
    from PyQt6.QtGui import QImage
    h, w = arr.shape[:2]
    arr = np.ascontiguousarray(arr)
    fmt = QImage.Format.Format_RGBA8888 if arr.shape[2] == 4 else QImage.Format.Format_RGB888
    QImage(arr.data, w, h, w * arr.shape[2], fmt).copy().save(str(path))
    return str(path)


def ffmpeg_texts(ff, video, texts, out, W, H, total, offset, run, tmp):
    """Pose tous les textes sur la vidéo (ffmpeg). texts : réglages + "debut_s" / "fin_s" (secondes)."""
    cmd = [ff, "-y", "-hide_banner", "-i", str(video)]
    fl = ["[0:v]format=gbrp[b0]"]
    last = "b0"
    for k, t in enumerate(texts, 1):
        t = full(t)
        lay = layer(t, W, H)
        png = save_png(lay, tmp / f"texte_{k}.png")
        cmd += ["-loop", "1", "-framerate", "60", "-t", f"{total:.3f}", "-i", png]
        a, b = float(t.get("debut_s", 0)) + offset, float(t.get("fin_s", total)) + offset
        en = f"enable='between(t,{a:.3f},{b:.3f})'"
        if t["mode"] == "incrustation":
            fl.append(f"[{k}:v]format=gbrp[t{k}]")
            fl.append(f"[{last}][t{k}]blend=all_mode=overlay:{en}[b{k}]")
        else:
            fl.append(f"[{last}][{k}:v]overlay=0:0:format=auto:{en}[b{k}]")
        last = f"b{k}"
    fl.append(f"[{last}]format=yuv420p[v]")
    cmd += ["-filter_complex", ";".join(fl), "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
            "-t", f"{total:.3f}", str(out)]
    run(cmd)
    return out

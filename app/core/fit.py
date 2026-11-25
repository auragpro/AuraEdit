"""Mise au format 1920x1080 SANS barres noires : les bords vides sont remplis par la vidéo en miroir
(effet « mosaïque » / Motion Tile avec bords en miroir)."""
import math
import re
import subprocess

from . import audio, vclip

_cache = {}


def size(path):
    """(largeur, hauteur) affichées de la vidéo (rotation comprise), ou None."""
    key = str(path)
    if key in _cache:
        return _cache[key]
    r = None
    try:
        out = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", *vclip.input_args(path)], capture_output=True,
                             stdin=subprocess.DEVNULL, creationflags=audio._NO_WINDOW,
                             timeout=30).stderr.decode("utf-8", "replace")
        m = re.search(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b", out)
        if m:
            r = (int(m[1]), int(m[2]))
            if re.search(r"rotation of -?(90|270)", out):
                r = (r[1], r[0])
    except Exception:                       # noqa: BLE001
        r = None
    _cache[key] = r
    return r


def _even(x):
    return max(2, int(round(x / 2)) * 2)


def mirror_fill(path, W, H):
    """Filtre ffmpeg (-vf) : remplit W x H, bords en miroir au lieu de barres noires."""
    s = size(path)
    if not s:
        return f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"
    w, h = s
    if abs(w / h - W / H) < 0.01:
        return f"scale={W}:{H}"
    if w / h < W / H:                     # trop étroite (ex. vidéo verticale) : miroir à gauche et à droite
        sw, sh = _even(w * H / h), H
        gap, tile, flip, stack = (W - sw) / 2, sw, "hflip", "hstack"
    else:                                 # trop large : miroir en haut et en bas
        sw, sh = W, _even(h * W / w)
        gap, tile, flip, stack = (H - sh) / 2, sh, "vflip", "vstack"
    n = max(1, math.ceil(gap / tile))
    k = 2 * n + 1
    parts = [f"scale={sw}:{sh},setsar=1,split={k}" + "".join(f"[t{j}]" for j in range(k))]
    for j in range(k):
        parts.append(f"[t{j}]{flip if (j - n) % 2 else 'null'}[u{j}]")
    off = int(n * tile - gap)
    crop = f"crop={W}:{H}:{off}:0" if flip == "hflip" else f"crop={W}:{H}:0:{off}"
    parts.append("".join(f"[u{j}]" for j in range(k)) + f"{stack}=inputs={k},{crop}")
    return ";".join(parts)

"""Réglages d'export (résolution, images/s, débit, vitesse d'encodage), gardés pour tous les projets."""
import json

from .project import config_dir

RESOLUTIONS = {"720p": (1280, 720), "1080p": (1920, 1080), "1440p": (2560, 1440), "4K": (3840, 2160)}
FPS_CHOICES = [24, 25, 30, 50, 60]
PRESETS = {"Rapide": "veryfast", "Équilibré": "medium", "Meilleure qualité (lent)": "slow"}


def defaults():
    return {"resolution": "1080p", "fps": 60, "debit": 50, "encodage": "Équilibré"}


def _file():
    return config_dir() / "export.json"


def load():
    d = defaults()
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            d.update({k: data[k] for k in d if k in data})
    except (OSError, ValueError):
        pass
    return clean(d)


def clean(d):
    c = defaults()
    c.update({k: d[k] for k in c if k in d})
    if c["resolution"] not in RESOLUTIONS:
        c["resolution"] = "1080p"
    c["fps"] = int(c["fps"]) if int(c["fps"] or 0) in FPS_CHOICES else 60
    c["debit"] = max(2, min(300, int(c["debit"] or 50)))
    if c["encodage"] not in PRESETS:
        c["encodage"] = "Équilibré"
    return c


def save(d):
    try:
        _file().write_text(json.dumps(clean(d), ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def ffmpeg_args(cfg):
    """Filtres + options d'encodage vidéo de l'export final."""
    cfg = clean(cfg)
    w, h = RESOLUTIONS[cfg["resolution"]]
    vf = []
    if (w, h) != (1920, 1080):
        vf.append(f"scale={w}:{h}:flags=lanczos")
    if cfg["fps"] != 60:
        vf.append(f"fps={cfg['fps']}")
    vf.append("format=yuv420p")
    b = cfg["debit"]
    return ["-vf", ",".join(vf), "-c:v", "libx264", "-preset", PRESETS[cfg["encodage"]], "-profile:v", "high",
            "-b:v", f"{b}M", "-maxrate", f"{int(b * 1.5)}M", "-bufsize", f"{b * 2}M", "-r", str(cfg["fps"])]

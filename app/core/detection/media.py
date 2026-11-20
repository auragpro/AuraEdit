"""Accès aux vidéos via FFmpeg (lecture audio, images, découpe)."""
import json
import os
import shutil
import subprocess

import numpy as np

from .. import vclip


def _bin(name):
    env = os.environ.get("AURAEDIT_" + name.upper())
    if env:
        return env
    path = shutil.which(name)
    if not path:
        raise RuntimeError(
            f"{name} introuvable. Installe FFmpeg et ajoute-le au PATH "
            f"(ou définis la variable AURAEDIT_{name.upper()}). Voir le README."
        )
    return path


def _run(args):
    proc = subprocess.run(args, capture_output=True)
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("FFmpeg a échoué : " + (msg[-1] if msg else "erreur inconnue"))
    return proc.stdout


def probe(path):
    """Renvoie largeur, hauteur, fps, durée et présence d'audio."""
    out = _run([_bin("ffprobe"), "-v", "error", "-print_format", "json",
                "-show_streams", "-show_format", vclip.source(path)])
    info = json.loads(out)
    video = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"Pas de piste vidéo dans {path}")

    def rate(txt):
        try:
            num, den = txt.split("/")
            return float(num) / float(den) if float(den) else 0.0
        except (ValueError, AttributeError):
            return 0.0

    fps = rate(video.get("avg_frame_rate")) or rate(video.get("r_frame_rate")) or 30.0
    duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    if vclip.length(path) is not None:
        duration = vclip.length(path)
    has_audio = any(s.get("codec_type") == "audio" for s in info["streams"])
    return {"width": int(video["width"]), "height": int(video["height"]),
            "fps": fps, "duration": duration, "has_audio": has_audio}


def extract_audio(path, sr):
    """Audio mono en float32."""
    raw = _run([_bin("ffmpeg"), "-nostdin", "-v", "error", *vclip.input_args(path), "-vn",
                "-ac", "1", "-ar", str(sr), "-f", "f32le", "pipe:1"])
    return np.frombuffer(raw, dtype=np.float32).copy()


def region_pixels(info, region):
    """Convertit une zone (x, y, l, h en fractions de l'écran) en pixels."""
    W, H = info["width"], info["height"]
    x, y, w, h = region
    px, py = int(round(x * W)), int(round(y * H))
    pw, ph = max(2, int(round(w * W))), max(2, int(round(h * H)))
    pw, ph = min(pw, W - px), min(ph, H - py)
    return px, py, pw, ph


def read_region(path, info, region, sample_fps, out_w):
    """Lit la zone de l'écran en niveaux de gris, à sample_fps images/s.

    Renvoie (images [N, h, w] uint8, temps [N] en secondes)."""
    px, py, pw, ph = region_pixels(info, region)
    out_h = max(2, int(round(ph * out_w / pw)))
    vf = f"fps={sample_fps},crop={pw}:{ph}:{px}:{py},scale={out_w}:{out_h}"
    raw = _run([_bin("ffmpeg"), "-nostdin", "-v", "error", *vclip.input_args(path), "-an",
                "-vf", vf, "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"])
    frames = np.frombuffer(raw, dtype=np.uint8)
    n = frames.size // (out_w * out_h)
    frames = frames[: n * out_w * out_h].reshape(n, out_h, out_w)
    times = np.arange(n) / float(sample_fps)
    return frames, times


def grab_frame(path, t):
    """Une image complète (BGR) au temps t."""
    import cv2
    raw = _run([_bin("ffmpeg"), "-nostdin", "-v", "error",
                *vclip.input_args(path, ss=t), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"])
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"Impossible de lire l'image à {t:.2f}s dans {path}")
    return img


def cut(path, start, end, out_path):
    """Découpe précise [start, end] (réencodage H.264)."""
    _run([_bin("ffmpeg"), "-nostdin", "-v", "error", "-y",
          *vclip.input_args(path, ss=start), "-t", f"{end - max(0.0, start):.3f}",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", str(out_path)])

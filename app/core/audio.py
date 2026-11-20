"""Lecture / écriture de fichiers audio (via FFmpeg intégré)."""
import shutil
import subprocess
import sys
import wave

import numpy as np

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0   # pas de fenêtre noire sous Windows


def ffmpeg_exe():
    """FFmpeg fourni avec l'app (imageio-ffmpeg), sinon celui du PC."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    path = shutil.which("ffmpeg")
    if path:
        return path
    raise RuntimeError("FFmpeg introuvable : impossible de lire les fichiers audio.")


def load(path, sr=44100, channels=1):
    """Audio en float32 (-1..1). channels=1 -> [n], channels=2 -> [n, 2]."""
    from . import vclip
    cmd = [ffmpeg_exe(), "-nostdin", "-v", "error", *vclip.input_args(path), "-vn",
           "-ac", str(channels), "-ar", str(sr), "-f", "f32le", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(f"Lecture impossible de {path} : {err[-1] if err else 'erreur inconnue'}")
    data = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    if channels > 1:
        data = data[: len(data) // channels * channels].reshape(-1, channels)
    return data


def save_wav(path, data, sr=44100):
    """Écrit un WAV 16 bits (mono [n] ou stéréo [n, 2])."""
    data = np.asarray(data, dtype=np.float32)
    channels = 1 if data.ndim == 1 else data.shape[1]
    pcm = (np.clip(data, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())

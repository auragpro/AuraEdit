"""Rendu de l'edit : intro + clips (dans l'ordre) + outro, sur la musique, en MP4 1080p.

Chaque morceau est d'abord remis au même format (1920x1080, 60 i/s, sans son), puis tout est
collé bout à bout et la musique est posée dessus. Les instants de chaque coupe sont gardés :
ils serviront à placer les shakes entre les clips.
"""
import json
import re
import subprocess
import tempfile
from pathlib import Path

from . import audio

W, H, FPS = 1920, 1080, 60


class RenderError(Exception):
    pass


class Cancelled(Exception):
    pass


def _run(cmd, is_cancelled=None):
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         creationflags=audio._NO_WINDOW)
    err = []
    for line in iter(p.stderr.readline, b""):
        err.append(line)
        if len(err) > 60:
            err.pop(0)
        if is_cancelled and is_cancelled():
            p.kill()
            p.wait()
            raise Cancelled()
    if p.wait() != 0:
        raise RenderError(b"".join(err[-12:]).decode("utf-8", "replace"))


def duration(path):
    out = subprocess.run([audio.ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True,
                         creationflags=audio._NO_WINDOW).stderr.decode("utf-8", "replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def segments(project):
    segs = []
    if project.intro:
        segs.append(("intro", project.intro))
    segs += [("clip", c) for c in dict.fromkeys(project.clips)]      # chaque clip une seule fois
    if project.outro:
        segs.append(("outro", project.outro))
    return [(k, p) for k, p in segs if p and Path(p).is_file()]


def render(project, output, progress=None, is_cancelled=None):
    """Fabrique le MP4. Renvoie {"fichier", "coupes": [s...], "segments": [...]}."""
    segs = segments(project)
    if not any(k == "clip" for k, _ in segs):
        raise RenderError("Aucun clip trouvé : ajoute des clips dans l'onglet Clips.")
    ff = audio.ffmpeg_exe()
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
          f"setsar=1,fps={FPS},format=yuv420p")
    steps = len(segs) + 1
    with tempfile.TemporaryDirectory(prefix="auraedit_") as tmp:
        tmp = Path(tmp)
        parts, info, t = [], [], 0.0
        for i, (kind, path) in enumerate(segs):
            if progress:
                progress(i / steps, f"Préparation {i + 1}/{len(segs)} : {Path(path).name}")
            part = tmp / f"{i:04d}.mp4"
            remap = project.remaps.get(path) if kind == "clip" else None
            if remap:
                from . import timeremap
                try:
                    timeremap.render(path, float(remap["debut"]), float(remap["fin"]), timeremap.load(), part,
                                     is_cancelled)
                except InterruptedError:
                    raise Cancelled()
                except (ValueError, KeyError, OSError) as e:
                    raise RenderError(f"Time remap impossible pour {Path(path).name} :\n{e}")
                d = duration(part)
                info.append({"type": kind, "fichier": str(path), "debut": round(t, 3), "duree": round(d, 3),
                             "time_remap": True})
                parts.append(part)
                t += d
                continue
            _run([ff, "-y", "-hide_banner", "-i", str(path), "-an", "-vf", vf, "-c:v", "libx264",
                  "-preset", "veryfast", "-crf", "18", str(part)], is_cancelled)
            d = duration(part)
            info.append({"type": kind, "fichier": str(path), "debut": round(t, 3), "duree": round(d, 3)})
            parts.append(part)
            t += d
        lst = tmp / "liste.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        if progress:
            progress(len(segs) / steps, "Assemblage et musique...")
        cmd = [ff, "-y", "-hide_banner", "-f", "concat", "-safe", "0", "-i", str(lst)]
        music = project.music if project.music and Path(project.music).is_file() else None
        if music:
            cmd += ["-i", music, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "320k", "-t", f"{t:.3f}"]
        cmd += ["-c:v", "copy", "-movflags", "+faststart", str(output)]
        _run(cmd, is_cancelled)
    if progress:
        progress(1.0, "Terminé")
    cuts = [s["debut"] for s in info[1:]]
    return {"fichier": str(output), "coupes": cuts, "segments": info, "duree": round(t, 3)}

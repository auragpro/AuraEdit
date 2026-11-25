"""Vidéos de comparaison : l'edit d'exemple à gauche, ton montage à droite, avec le son de l'edit."""
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import audio, vclip

PW, PH, PFPS = 640, 360, 30


def _run(cmd, cancelled=None):
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                         creationflags=audio._NO_WINDOW)
    _, err = p.communicate()
    if cancelled and cancelled():
        raise InterruptedError()
    if p.returncode != 0:
        raise RuntimeError(err.decode("utf-8", "replace")[-600:])


def _fit(w, h):
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={PFPS},format=yuv420p")


def _side(left, right, out, w, h, cancelled=None):
    ff = audio.ffmpeg_exe()
    _run([ff, "-y", "-hide_banner", "-i", str(left), "-i", str(right), "-filter_complex",
          f"[0:v]{_fit(w, h)}[l];[1:v]{_fit(w, h)}[r];[l][r]hstack=inputs=2[v]",
          "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
          "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], cancelled)
    return str(out)


def quick_preview(edit, plans, out, progress=None, cancelled=None):
    """Aperçu rapide (sans ralentis) : plans = [(chemin du clip ou None, début dans le clip, durée)]."""
    ff = audio.ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="auraedit_cmp_") as tmp:
        tmp = Path(tmp)
        done = [0]

        def one(k):
            path, start, d = plans[k]
            part = tmp / f"{k:04d}.mp4"
            d = max(0.04, d)
            if path and vclip.exists(path):
                _run([ff, "-y", "-hide_banner", *vclip.input_args(path, ss=max(0.0, start)), "-an", "-vf",
                      _fit(PW, PH) + f",tpad=stop_mode=clone:stop_duration={d:.3f}", "-t", f"{d:.4f}",
                      "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", str(part)], cancelled)
            else:                                   # plan sans clip : écran noir
                _run([ff, "-y", "-hide_banner", "-f", "lavfi", "-i", f"color=c=black:s={PW}x{PH}:r={PFPS}:d={d:.4f}",
                      "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", str(part)],
                     cancelled)
            done[0] += 1
            if progress:
                progress(f"Aperçu : plan {done[0]}/{len(plans)}", 0.9 * done[0] / max(1, len(plans)))
            return part

        with ThreadPoolExecutor(max_workers=4) as pool:
            parts = list(pool.map(one, range(len(plans))))
        lst = tmp / "liste.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        right = tmp / "droite.mp4"
        _run([ff, "-y", "-hide_banner", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(right)],
             cancelled)
        if progress:
            progress("Assemblage côte à côte...", 0.95)
        return _side(edit, right, out, PW, PH, cancelled)


def side_by_side(edit, result, out, cancelled=None):
    """L'edit d'exemple à gauche, le vrai rendu à droite (960x540 chacun)."""
    return _side(edit, result, out, 960, 540, cancelled)


def open_file(path):
    import os
    import sys
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(path)])

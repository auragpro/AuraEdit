"""Transitions d'une vidéo (changements de plan) + un son de kill sur chacune."""
import random
import re
import subprocess
from pathlib import Path

from . import audio
from . import sound_ai as sa

NOT_KILL = set(sa.ALIGN_PEAK) | {"impact"}


def detect_cuts(path, threshold=0.3, min_gap=0.25):
    """Moments (s) où l'image change d'un coup (transition, nouveau clip)."""
    cmd = [audio.ffmpeg_exe(), "-hide_banner", "-nostdin", "-i", str(path), "-an", "-sn",
           "-vf", f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL,
                          creationflags=audio._NO_WINDOW)
    text = proc.stderr.decode("utf-8", errors="ignore")
    if proc.returncode != 0 and "pts_time" not in text:
        raise RuntimeError("Impossible de lire la vidéo de l'edit.")
    cuts = []
    for m in re.finditer(r"pts_time:([0-9.]+)", text):
        t = float(m.group(1))
        if not cuts or t - cuts[-1] >= min_gap:
            cuts.append(t)
    return cuts


def kill_sounds(library):
    """Seulement les sons de kill (pas les wooshs, risers, impacts)."""
    kill = [s for s in library if s.category == "kill"]
    return kill or [s for s in library if s.category not in NOT_KILL] or list(library)


def place_kills(cuts, analysis, library, ai, seed=None):
    rng = random.Random(seed)
    pool = kill_sounds(library)
    if not pool:
        raise ValueError("Aucun son de kill dans ton dossier.")
    out, last = [], None
    for t in cuts:
        w = [ai.sound_score(s) * (0.3 if s.path == last else 1.0) for s in pool]
        snd = rng.choices(pool, weights=w)[0]
        ctx, role = sa.context_at(analysis, t) if analysis is not None else ("temps_fort|moyen", "temps_fort")
        out.append(sa.Placement(t=round(t, 3), category=snd.category, sound=snd.path, ctx=ctx,
                                role=role, gain=1.0))
        last = snd.path
    return out

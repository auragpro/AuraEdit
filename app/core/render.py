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

from . import audio, vclip

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
    if vclip.length(path) is not None:
        return vclip.length(path)
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
    return [(k, p) for k, p in segs if p and vclip.exists(p)]


def _overlays(project, info, video, is_list, tmp, ff, total, progress, is_cancelled):
    """Vidéos superposées (fond vert) : posées sur toute la vidéo, à partir du début de leur clip,
    et elles peuvent continuer sur les clips suivants."""
    ovs = getattr(project, "overlays", None) or {}
    items = []
    for s in info:
        ov = ovs.get(s["fichier"]) if s["type"] == "clip" else None
        if ov and ov.get("fichier") and Path(ov["fichier"]).is_file():
            items.append({**ov, "t0": s["debut"], "clip_duree": s["duree"]})
    if not items:
        return video, is_list
    from . import chroma
    src = video
    if is_list:
        src = tmp / "base_ov.mp4"
        _run([ff, "-y", "-hide_banner", "-f", "concat", "-safe", "0", "-i", str(video), "-c:v", "copy", str(src)],
             is_cancelled)
    out = tmp / "superpose.mp4"
    try:
        chroma.apply_timeline(src, out, items, W, H, FPS, total, is_cancelled,
                              (lambda f: progress(f, "Superposition fond vert...")) if progress else None)
    except InterruptedError:
        raise Cancelled()
    except (RuntimeError, OSError, ValueError) as e:
        raise RenderError(f"Superposition impossible :\n{e}")
    return out, False


def render(project, output, progress=None, is_cancelled=None, export=None):
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
        import os
        import threading
        from concurrent.futures import ThreadPoolExecutor
        lock = threading.Lock()
        done = [0]
        # time remaps : déjà multi-cœurs et gourmands en mémoire -> 2 à la fois max (1 sur petit PC)
        remap_slots = threading.Semaphore(2 if (os.cpu_count() or 4) >= 8 else 1)

        def tick(txt):
            if progress:
                with lock:
                    progress(min(0.97, done[0] / steps), txt)

        def prep(i, kind, path):
            """Prépare un plan (encodage en .mp4). Renvoie (fichier, durée, time_remap)."""
            part = tmp / f"{i:04d}.mp4"
            remap = project.remaps.get(path) if kind == "clip" else None
            plan = None
            if kind == "clip":                                   # durée du plan : jusqu'au clip suivant
                from . import markers as _mk
                plan = ((getattr(project, "plans", None) or {}).get(path)
                        or (remap or {}).get("plan") or _mk.gap_for(project, path))
            if remap:
                from . import timeremap
                try:
                    name = vclip.name(path)
                    rcfg = timeremap.cfg_for(remap)
                    if plan:                                     # durée = plan jusqu'au clip suivant
                        rcfg["duree_ralenti"] = max(0.1, plan - int(rcfg.get("frames_retour", 7)) / timeremap.FPS)
                    with remap_slots:
                        timeremap.render(path, float(remap["debut"]), float(remap["fin"]), rcfg, part, is_cancelled,
                                         (lambda f, txt, i=i, name=name: tick(f"Clip {i + 1}/{len(segs)} — {txt} ({name})"))
                                         if progress else None)
                except InterruptedError:
                    raise Cancelled()
                except (ValueError, KeyError, OSError) as e:
                    raise RenderError(f"Time remap impossible pour {vclip.name(path)} :\n{e}")
                return part, duration(part), True
            ss = None
            if kind == "clip":                                   # début choisi (clip sans time remap)
                from . import timeremap as _tr
                ss = _tr.clip_starts().get(str(path))
            cut = []
            vfx = vf
            if plan:                                             # coupé pile au clip suivant
                vfx = vf + f",tpad=stop_mode=clone:stop_duration={plan:.3f}"
                cut = ["-t", f"{plan:.4f}"]
            _run([ff, "-y", "-hide_banner", *vclip.input_args(path, ss=ss), "-an", "-vf", vfx, *cut,
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-threads", "4", str(part)], is_cancelled)
            return part, duration(part), False

        def job(i, kind, path):
            r = prep(i, kind, path)
            with lock:
                done[0] += 1
            tick(f"Préparation des clips : {done[0]}/{len(segs)}")
            return r

        # plusieurs clips préparés en même temps (même réglages, même qualité : juste plus rapide)
        workers = max(2, min(6, (os.cpu_count() or 4) // 2))
        tick(f"Préparation des clips : 0/{len(segs)}")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(job, i, kind, path) for i, (kind, path) in enumerate(segs)]
            try:
                results = [f.result() for f in futs]
            except BaseException:
                for f in futs:
                    f.cancel()
                raise
        parts, info, t = [], [], 0.0
        for (kind, path), (part, d, tr_) in zip(segs, results):
            item = {"type": kind, "fichier": str(path), "debut": round(t, 3), "duree": round(d, 3)}
            if tr_:
                item["time_remap"] = True
            info.append(item)
            parts.append(part)
            t += d
        lst = tmp / "liste.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        if progress:
            progress(len(segs) / steps, "Assemblage et musique...")
        cuts = [s["debut"] for s in info[1:]]
        video = lst
        from . import shake
        scfg = getattr(project, "shakes", None)
        if shake.active(scfg, cuts):
            base = tmp / "base.mp4"
            _run([ff, "-y", "-hide_banner", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "copy",
                  str(base)], is_cancelled)
            video = tmp / "shake.mp4"
            try:
                shake.apply(base, video, cuts, scfg, W, H, FPS, int(t * FPS) + 1, is_cancelled,
                            (lambda f, txt: progress((len(segs) + f * 0.9) / steps, txt)) if progress else None)
            except InterruptedError:
                raise Cancelled()
            except (RuntimeError, OSError) as e:
                raise RenderError(f"Shakes impossibles :\n{e}")
        video, is_list = _overlays(project, info, video, video == lst, tmp, ff, int(t * FPS) + 1,
                                   (lambda f, txt: progress(min(0.98, (len(segs) + 0.5 + f * 0.4) / steps), txt))
                                   if progress else None, is_cancelled)
        if is_list:
            cmd = [ff, "-y", "-hide_banner", "-f", "concat", "-safe", "0", "-i", str(lst)]
        else:
            cmd = [ff, "-y", "-hide_banner", "-i", str(video)]
        music = project.music if project.music and Path(project.music).is_file() else None
        if music:
            cmd += ["-i", music, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "320k", "-t", f"{t:.3f}"]
        from . import export_cfg
        if progress:
            progress(min(0.99, (len(segs) + 0.9) / steps), "Encodage final (qualité d'export)...")
        cmd += export_cfg.ffmpeg_args(export or export_cfg.load()) + ["-movflags", "+faststart", str(output)]
        _run(cmd, is_cancelled)
    if progress:
        progress(1.0, "Terminé")
    return {"fichier": str(output), "coupes": cuts, "segments": info, "duree": round(t, 3)}

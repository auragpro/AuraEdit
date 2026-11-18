"""Apprendre d'un edit déjà fait : l'IA « écoute » l'edit et retrouve tes sound kills.

Étapes
------
1. Caler la musique d'origine dans l'edit (l'edit peut commencer par une intro, la musique
   peut démarrer plus loin dans le morceau, son volume peut varier).
2. Retirer la musique : ce qui reste, ce sont les sons ajoutés (sound kills).
3. Pour chaque son de ta bibliothèque, chercher où son « empreinte » apparaît dans ce reste.
4. Replacer chaque son trouvé dans la musique (drop ? temps fort ? caisse claire ?) et
   l'apprendre — ainsi que les moments où tu n'as PAS mis de son.
"""
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import audio
from . import music_analysis as ma
from . import sound_ai as sa

SR = ma.SR
DT = ma.DT
MATCH_THRESHOLD = 0.66        # ressemblance mini (0..1) pour dire « ce son est là »
MAX_TEMPLATE_S = 1.5
ONSET_MATCH = 0.42          # ressemblance mini quand un départ net est entendu


@dataclass
class Detection:
    t: float                  # temps dans la MUSIQUE (convention de placement de l'IA)
    t_edit: float             # temps dans l'edit
    sound: str
    category: str
    score: float
    role: str = ""
    ctx: str = ""
    keep: bool = True         # l'utilisateur peut décocher une détection douteuse


@dataclass
class EditExample:
    edit_path: str
    music_path: str
    shift: float              # temps_edit = temps_musique + shift
    start: float              # partie de la musique utilisée dans l'edit (s)
    end: float
    gain: float               # volume moyen de la musique dans l'edit
    detections: list = field(default_factory=list)
    analysis: object = None


# ---------------------------------------------------------------- outils ----

def _xcorr(a, b):
    """Corrélation croisée complète par FFT. Indice k <=> a décalé de (k - (len(b)-1))."""
    n = len(a) + len(b) - 1
    size = 1 << (n - 1).bit_length()
    r = np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size)), size)
    # r[k] = sum a[i+k] b[i] pour k >= 0, et r[size+k] pour k < 0
    return np.concatenate([r[size - (len(b) - 1):], r[:len(a)]])


def _znorm(x):
    x = np.asarray(x, dtype=np.float64)
    return (x - x.mean()) / (x.std() + 1e-9)


def _frame_similarity(E, M, lag):
    """Ressemblance (0..1) entre l'edit et la musique décalée de `lag` trames, sur leur partie commune."""
    a0, a1 = max(0, lag), min(len(E), lag + len(M))
    if a1 - a0 < 10:
        return -1.0
    X, Y = E[a0:a1], M[a0 - lag:a1 - lag]
    num = (X * Y).sum(1)
    den = np.linalg.norm(X, axis=1) * np.linalg.norm(Y, axis=1) + 1e-9
    w = np.linalg.norm(Y, axis=1)                       # les passages forts de la musique comptent plus
    return float((num / den * w).sum() / (w.sum() + 1e-9))


def find_shift(edit, music):
    """Décalage (en échantillons) tel que edit[i] ≈ music[i - shift]."""
    e_spec, _ = ma.band_spectrogram(edit)
    m_spec, _ = ma.band_spectrogram(music)
    oe = _znorm(ma._flux(e_spec))
    om = _znorm(ma._flux(m_spec))
    c = _xcorr(oe, om)
    lags = np.arange(len(c)) - (len(om) - 1)
    # plusieurs candidats (une musique répétitive se ressemble à un temps près) départagés
    # par une comparaison complète des spectres
    order = np.argsort(-c)
    cands = []
    for k in order:
        if all(abs(lags[k] - x) > 3 for x in cands):
            cands.append(int(lags[k]))
        if len(cands) >= 12:
            break
    Ec = e_spec - e_spec.mean(1, keepdims=True)
    Mc = m_spec - m_spec.mean(1, keepdims=True)
    best = max(cands, key=lambda L: max(_frame_similarity(Ec, Mc, L + d) for d in (-1, 0, 1)))
    lag_frames = max((best + d for d in (-1, 0, 1)), key=lambda L: _frame_similarity(Ec, Mc, L))
    coarse = lag_frames * ma.HOP
    # affinage à l'échantillon près sur un extrait de 8 s au milieu de la partie commune
    m0 = max(0, -coarse)
    m1 = min(len(music), len(edit) - coarse)
    if m1 - m0 < SR:
        return coarse
    mid = (m0 + m1) // 2
    seg = music[max(m0, mid - 4 * SR):min(m1, mid + 4 * SR)]
    s0 = max(m0, mid - 4 * SR)
    w = 2 * ma.HOP
    a0, a1 = max(0, s0 + coarse - w), min(len(edit), s0 + coarse + len(seg) + w)
    win = edit[a0:a1]
    if len(win) < len(seg):
        return coarse
    c = _xcorr(win, seg)[len(seg) - 1:len(seg) - 1 + len(win) - len(seg) + 1]
    return int(a0 + np.argmax(c) - s0)


def _aligned(music, shift, n):
    out = np.zeros(n, dtype=np.float32)
    a, b = max(0, shift), min(n, shift + len(music))
    if b > a:
        out[a:b] = music[a - shift:b - shift]
    return out


def residual(edit, music_aligned, present=None, block_s=2.0):
    """Spectrogramme de l'edit SANS la musique (log).

    Le volume de la musique est estimé bande par bande, par blocs de ~2 s : ça compense
    un égaliseur, une compression ou un fondu appliqué à la musique dans l'edit.
    Les sons courts (sound kills) ne faussent pas l'estimation (médiane).
    """
    E, _ = ma.band_spectrogram(edit, linear=True)
    M, _ = ma.band_spectrogram(music_aligned, linear=True)
    n = min(len(E), len(M))
    E, M = E[:n], M[:n]
    ref = M.max(0, keepdims=True) * 0.02
    ratio = np.where(M > ref, E / np.maximum(M, 1e-12), np.nan)
    if present is not None:                      # l'intro / l'outro ne comptent pas
        ratio[~present[:n]] = np.nan
    k = max(4, int(block_s / DT))
    nb = -(-n // k)
    G = np.full((nb, E.shape[1]), np.nan)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            for i in range(nb):
                G[i] = np.nanmedian(ratio[i * k:(i + 1) * k], axis=0)
            # bande sans musique dans un bloc : on prend la valeur globale de la bande
            glob = np.nanmedian(G, axis=0)
    glob = np.nan_to_num(glob, nan=0.0)
    G = np.where(np.isnan(G), glob[None, :], G)
    centers = (np.arange(nb) + 0.5) * k
    frames = np.arange(n)
    g = np.stack([np.interp(frames, centers, G[:, j]) for j in range(G.shape[1])], axis=1)
    R = np.maximum(E - 1.2 * g * M, 0)                    # 1.2 : marge pour les petits écarts
    return np.log1p(100 * R), np.median(g, axis=1)


# ------------------------------------------------------------- empreintes ----

class Template:
    def __init__(self, sound):
        self.sound = sound
        y = audio.load(sound.path, SR, 1)
        spec, _ = ma.band_spectrogram(y)
        lin, _ = ma.band_spectrogram(y, linear=True)
        energy = spec.sum(1)
        peak = float(energy.max()) or 1.0
        onset = int(np.argmax(energy > 0.1 * peak))
        start = max(0, onset - 1)
        active = np.where(energy > 0.02 * peak)[0]
        end = int(active.max()) + 1 if active.size else start + 4
        end = min(end, start + int(MAX_TEMPLATE_S / DT), len(spec))
        self.t = spec[start:max(end, start + 4)]
        self.lin = lin[start:start + len(self.t)]
        self.start_frame = start
        # ancre de placement (en s depuis le début du son), comme le rendu de l'IA
        mono = np.abs(y)
        pk = float(mono.max()) or 1.0
        k = max(1, int(0.01 * SR))
        env = np.convolve(mono, np.ones(k) / k, mode="same")
        anchor = np.argmax(env) if sound.category in sa.ALIGN_PEAK else np.argmax(mono > 0.1 * pk)
        self.anchor_s = anchor / SR


def _ncc_curve(FR, csum, csum2, T, B, tmpl, size):
    L = len(tmpl)
    if L >= T:
        return np.zeros(0)
    t = tmpl - tmpl.mean()
    t /= np.linalg.norm(t) or 1.0
    FT = np.fft.rfft(t, size, axis=0)
    num = np.fft.irfft((FR * np.conj(FT)).sum(1), size)[:T - L + 1]
    s1 = csum[L:] - csum[:-L]
    s2 = csum2[L:] - csum2[:-L]
    var = np.maximum(s2 - s1 ** 2 / (L * B), 1e-9)
    return num / np.sqrt(var)


def residual_onsets(res_log):
    """Départs de sons dans le reste (là où « quelque chose » arrive en plus de la musique)."""
    flux = np.maximum(np.diff(res_log, axis=0, prepend=res_log[:1]), 0).sum(1)
    if not flux.size:
        return np.zeros(0, int), flux
    k = int(2.0 / DT)
    pad = np.pad(flux, (k // 2, k // 2), mode="edge")
    local = np.median(np.lib.stride_tricks.sliding_window_view(pad, k + 1 - (k % 2)), axis=-1)[:len(flux)]
    floor = 0.25 * np.percentile(flux, 99)
    thr = np.maximum(3.0 * local, floor)
    peaks = np.asarray(ma._peaks(flux, 0.0, 3), dtype=int)
    return peaks[flux[peaks] > thr[peaks]] if peaks.size else peaks, flux


def find_sounds(res_log, templates, threshold=MATCH_THRESHOLD, onset_threshold=ONSET_MATCH,
                progress=None):
    """Positions (trame de départ, score, empreinte) de tes sons dans le reste.

    Deux façons de trouver un son :
    * son empreinte ressemble très fort au reste (score >= threshold), n'importe où ;
    * un départ net est entendu dans le reste et, à cet endroit, un de tes sons
      ressemble assez (score >= onset_threshold) : utile quand la musique est forte.
    """
    T, B = res_log.shape
    size = 1 << (T + int(MAX_TEMPLATE_S / DT) + 1).bit_length()
    X = res_log.astype(np.float64)
    FR = np.fft.rfft(X, size, axis=0)
    csum = np.concatenate([[0.0], np.cumsum(X.sum(1))])
    csum2 = np.concatenate([[0.0], np.cumsum((X ** 2).sum(1))])
    loud = X.sum(1)
    gate = 0.15 * np.percentile(loud, 99) if T else 0          # ignore le « vide »
    onsets, _ = residual_onsets(res_log)
    found = []
    curves = []
    for i, tp in enumerate(templates):
        c = _ncc_curve(FR, csum, csum2, T, B, tp.t, size)
        curves.append(c)
        if c.size:
            L = len(tp.t)
            for k in ma._peaks(c, threshold, max(2, L // 2)):
                if loud[k:k + L].mean() >= gate:
                    found.append((int(k), float(c[k]), tp))
        if progress:
            progress(i + 1, len(templates))
    for o in onsets:
        best = None
        for c, tp in zip(curves, templates):
            if not c.size:
                continue
            a, b = max(0, o - 2), min(len(c), o + 2)
            if b <= a:
                continue
            k = a + int(np.argmax(c[a:b]))
            if best is None or c[k] > best[1]:
                best = (k, float(c[k]), tp)
        # les « boom » graves ressemblent aux grosses caisses de la musique : plus exigeant
        need = onset_threshold + (0.12 if best and best[2].sound.category == "impact" else 0.0)
        if best and best[1] >= need:
            found.append(best)
    # Choix final « un par un » : on prend le son le plus ressemblant, on le RETIRE du reste,
    # puis on revérifie les suivants. Deux sons superposés (woosh + tir au drop) ne
    # produisent ainsi pas de faux sons fantômes.
    found.sort(key=lambda f: -f[1])
    lin = np.expm1(X) / 100.0
    kept = []
    for k, score, tp in found:
        L = len(tp.t)
        if k + L > T:
            continue
        need = threshold if score >= threshold else onset_threshold
        if kept:
            W = np.log1p(100 * lin[k:k + L])
            t0 = tp.t - tp.t.mean()
            t0 /= np.linalg.norm(t0) or 1.0
            var = max((W ** 2).sum() - W.sum() ** 2 / W.size, 1e-9)
            score = float((t0 * W).sum() / np.sqrt(var))
            if score < need:
                continue
        peak_like = tp.sound.category in sa.ALIGN_PEAK
        if any(abs(k - k2) * DT < 0.09 and (tp2.sound.category in sa.ALIGN_PEAK) == peak_like
               for k2, _, tp2 in kept):
            continue
        kept.append((k, score, tp))
        # retire ce son du reste (volume estimé là où le son est fort)
        seg = lin[k:k + L]
        mask = tp.lin > 0.1 * tp.lin.max()
        if mask.any():
            alpha = float(np.median(seg[mask] / tp.lin[mask]))
            lin[k:k + L] = np.maximum(seg - alpha * tp.lin, 0)
    return kept


# ----------------------------------------------------------------- écoute ----

def listen(edit_path, music_path, library, progress=None):
    """Analyse un edit fini. Renvoie un EditExample avec les sound kills retrouvés."""
    def step(txt, frac):
        if progress:
            progress(txt, frac)

    if not library:
        raise ValueError("Choisis d'abord ton dossier de sons : l'IA s'en sert pour reconnaître tes sound kills.")
    step("Lecture de l'edit et de la musique...", 0.02)
    edit = audio.load(edit_path, SR, 1)
    music = audio.load(music_path, SR, 1)
    if len(edit) < SR or len(music) < SR:
        raise ValueError("Fichier audio trop court ou vide.")

    step("Calage de la musique dans l'edit...", 0.12)
    shift = find_shift(edit, music)
    m_al = _aligned(music, shift, len(edit))
    overlap = np.count_nonzero(m_al) / max(1, min(len(music), len(edit)))
    if overlap < 0.2:
        raise ValueError("La musique n'a pas été retrouvée dans l'edit. Est-ce bien la musique d'origine ?")
    # contrôle : au bon calage, l'edit ressemble NETTEMENT plus à la musique qu'à côté
    e_spec, _ = ma.band_spectrogram(edit)
    a_spec, _ = ma.band_spectrogram(m_al)
    m_spec, _ = ma.band_spectrogram(music)
    n = min(len(e_spec), len(a_spec))
    Ec = e_spec - e_spec.mean(1, keepdims=True)
    Mc = m_spec - m_spec.mean(1, keepdims=True)
    lag = int(round(shift / ma.HOP))
    best = _frame_similarity(Ec, Mc, lag)
    others = [_frame_similarity(Ec, Mc, lag + d) for d in (-40, -25, -13, -7, 7, 13, 25, 40)]
    if best - float(np.median(others)) < 0.06:
        raise ValueError("La musique n'a pas été retrouvée dans l'edit. Est-ce bien la musique d'origine "
                         "(la même version, sans les sons) ?")

    step("Retrait de la musique...", 0.25)
    # la musique « joue » là où le spectre de l'edit ressemble à celui de la musique (fenêtre ~1 s)
    X = e_spec[:n] - e_spec[:n].mean(1, keepdims=True)
    Y = a_spec[:n] - a_spec[:n].mean(1, keepdims=True)
    k = int(1.0 / DT)
    num = np.convolve((X * Y).sum(1), np.ones(k), "same")
    den = np.sqrt(np.convolve((X * X).sum(1), np.ones(k), "same") * np.convolve((Y * Y).sum(1), np.ones(k), "same")) + 1e-9
    local = num / den
    mask = local > max(0.5, 0.72 * float(np.median(local)))
    present = np.where(mask)[0]
    if present.size == 0:
        raise ValueError("La musique n'a pas été retrouvée dans l'edit. Est-ce bien la musique d'origine ?")
    # partie de l'edit où la musique joue (on retire l'intro et l'outro, pas les trous :
    # un gros sound kill peut masquer la musique un instant)
    mask = np.zeros(n, bool)
    mask[present[0]:present[-1] + 1] = True
    edit_from, edit_to = present[0] * DT, (present[-1] + 1) * DT
    res, g = residual(edit, m_al, mask)
    res[~mask[:len(res)]] = 0.0                      # rien à chercher dans l'intro / l'outro
    med = float(np.median(g[mask[:len(g)]])) if mask[:len(g)].any() else 0.0
    step("Chargement de tes sons...", 0.35)
    templates = []
    for i, s in enumerate(library):
        try:
            templates.append(Template(s))
        except (RuntimeError, ValueError):
            continue                                   # son illisible : ignoré
        if i % 10 == 0:
            step(f"Chargement de tes sons... ({i + 1}/{len(library)})", 0.35 + 0.2 * (i + 1) / len(library))

    step("Recherche de tes sound kills...", 0.55)
    kept = find_sounds(res, templates, progress=lambda a, b: step(
        f"Recherche de tes sound kills... ({a}/{b})", 0.55 + 0.35 * a / b))

    step("Analyse de la musique...", 0.92)
    analysis = ma.analyze(music)
    shift_s = shift / SR
    start = max(0.0, edit_from - shift_s)
    end = min(len(music) / SR, edit_to - shift_s)
    drops = analysis.drops
    dets = []
    for k, score, tp in kept:
        t_edit = (k - tp.start_frame) * DT + tp.anchor_s
        t = t_edit - shift_s
        if not start + 0.15 <= t <= end - 0.05:
            continue
        cat = tp.sound.category
        if cat in sa.ALIGN_PEAK and any(abs(t - d) < 0.2 for d in drops):
            role = "avant_drop"
            e = sa._energy_label(sa._energy_at(analysis.beats, t))
            ctx = f"avant_drop|{e}"
        else:
            ctx, role = sa.context_at(analysis, t)
        dets.append(Detection(t=round(float(t), 3), t_edit=round(float(t_edit), 3), sound=tp.sound.path,
                              category=cat, score=round(float(score), 2), role=role, ctx=ctx))
    dets.sort(key=lambda d: d.t)
    step("Terminé", 1.0)
    return EditExample(str(edit_path), str(music_path), shift_s, start, end, med, dets, analysis)


def apply(ai, example):
    """L'IA apprend de l'edit : chaque son retrouvé + chaque moment laissé sans son."""
    kept = [d for d in example.detections if d.keep]
    for d in kept:
        ai.learn_add(d.ctx, d.category, d.sound)
    # moments de la musique (dans la partie utilisée) où tu n'as rien mis
    negatives = 0
    for m in sa.moments(example.analysis):
        if not example.start <= m.t <= example.end:
            continue
        if m.role == "avant_drop":
            has = any(d.role == "avant_drop" and abs(d.t - m.t) < 0.2 for d in kept)
        else:
            has = any(d.role != "avant_drop" and abs(d.t - m.t) < 0.15 for d in kept)
        if not has:
            ai._bump_place(m.ctx, False)
            negatives += 1
    ai.decisions += negatives
    ai.save()
    return len(kept), negatives

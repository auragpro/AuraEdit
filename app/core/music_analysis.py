"""Analyse d'une musique : tempo, beats, temps forts, drops, attaques de voix, paroles.

Tout est fait avec numpy (pas de librairie lourde) :
  - « flux spectral » : à quel point le son change d'un instant à l'autre -> les attaques ;
  - tempo : on cherche la période qui se répète le plus dans ces attaques ;
  - beats : programmation dynamique (méthode d'Ellis) pour poser une grille régulière
    qui tombe au mieux sur les attaques ;
  - drops : mesures où l'énergie saute brutalement ;
  - voix : attaques dans la partie « tenue » (harmonique) du son, entre 300 et 3400 Hz.
"""
import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np

SR = 22050
N_FFT = 2048
HOP = 512
DT = HOP / SR                     # ~23 ms par trame
ONSET_LAG = 0.021                 # avance mesurée de la détection d'attaques (compensée)
N_BANDS = 96


@dataclass
class Beat:
    t: float
    strength: float      # force de l'attaque (0..1)
    low: float           # présence de grosse caisse (0..1)
    mid: float           # présence de caisse claire (0..1)
    energy: float        # énergie de la musique autour du beat (0..1)
    bar_pos: int         # position dans la mesure (0 = temps fort)
    drop: bool = False


@dataclass
class Analysis:
    duration: float
    tempo: float
    beats: list
    vocal_onsets: list = field(default_factory=list)
    lyric_words: list = field(default_factory=list)       # [(t, mot)]
    keyword_hits: list = field(default_factory=list)      # [(t, mot)]
    envelope: list = field(default_factory=list)          # forme d'onde réduite (dessin)

    @property
    def drops(self):
        return [b.t for b in self.beats if b.drop]


# ---------------------------------------------------------------- outils ----

def _frames(y):
    """Trames centrées : la trame i couvre le son autour de i * DT secondes."""
    n = 1 + max(0, y.size - 1) // HOP
    n = max(n, 1)
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]   # sur le signal complété
    return n, idx


def _pad(y):
    return np.pad(y, (N_FFT // 2, N_FFT // 2 + HOP))


def band_spectrogram(y):
    """Spectrogramme en N_BANDS bandes logarithmiques (30 Hz -> 11 kHz), en log."""
    n, idx = _frames(y)
    y = _pad(y)
    win = np.hanning(N_FFT).astype(np.float32)
    freqs = np.fft.rfftfreq(N_FFT, 1 / SR)
    edges = np.geomspace(30, 11000, N_BANDS + 1)
    bin_band = np.clip(np.searchsorted(edges, freqs) - 1, -1, N_BANDS)
    valid = (bin_band >= 0) & (bin_band < N_BANDS)
    out = np.zeros((n, N_BANDS), dtype=np.float32)
    counts = np.bincount(bin_band[valid], minlength=N_BANDS).astype(np.float32)
    counts[counts == 0] = 1
    for start in range(0, n, 1024):                      # par blocs : peu de mémoire
        sl = idx[start:start + 1024]
        mag = np.abs(np.fft.rfft(y[sl] * win, axis=1)).astype(np.float32)
        acc = np.zeros((mag.shape[0], N_BANDS), dtype=np.float32)
        for b in range(N_BANDS):
            m = bin_band == b
            if m.any():
                acc[:, b] = mag[:, m].sum(1)
        out[start:start + len(sl)] = acc / counts
    centers = np.sqrt(edges[:-1] * edges[1:])
    return np.log1p(100 * out), centers


def _flux(spec, mask=None):
    d = np.maximum(np.diff(spec, axis=0, prepend=spec[:1]), 0)
    if mask is not None:
        d = d[:, mask]
    return d.sum(1)


def _normalize(x):
    x = np.asarray(x, dtype=np.float64)
    hi = np.percentile(x, 99) if x.size else 1
    return np.clip(x / hi, 0, 1) if hi > 0 else np.zeros_like(x)


def _smooth(x, n):
    if n <= 1:
        return x
    k = np.hanning(n + 2)[1:-1]
    return np.convolve(x, k / k.sum(), mode="same")


def _peaks(x, threshold, min_dist):
    """Indices des maximums locaux > threshold, espacés d'au moins min_dist."""
    cand = np.where((x[1:-1] > x[:-2]) & (x[1:-1] >= x[2:]) & (x[1:-1] > threshold))[0] + 1
    keep = []
    for i in cand[np.argsort(-x[cand])]:
        if all(abs(i - k) >= min_dist for k in keep):
            keep.append(i)
    return sorted(keep)


# ----------------------------------------------------------- tempo/beats ----

def estimate_tempo(onset, lo=70, hi=180):
    o = onset - onset.mean()
    ac = np.correlate(o, o, mode="full")[len(o) - 1:]
    lags = np.arange(len(ac))
    bpm = np.where(lags > 0, 60 / (lags * DT + 1e-9), 0)
    valid = (bpm >= lo) & (bpm <= hi)
    if not valid.any():
        return 120.0
    # légère préférence autour de 120 BPM (les tempos de musique les plus courants)
    weight = np.exp(-0.5 * (np.log2(np.maximum(bpm, 1) / 120) / 1.0) ** 2)
    score = np.where(valid, ac * weight, -np.inf)
    lag = int(np.argmax(score))
    # affinage parabolique
    if 1 <= lag < len(ac) - 1:
        a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
        den = a - 2 * b + c
        lag = lag + (0.5 * (a - c) / den if den != 0 else 0)
    return float(60 / (lag * DT))


def track_beats(onset, tempo, tightness=100):
    """Programmation dynamique : grille de beats régulière qui suit les attaques."""
    period = 60 / tempo / DT
    n = len(onset)
    o = onset / (onset.std() + 1e-9)
    score = o.copy()
    back = -np.ones(n, dtype=int)
    lo, hi = int(round(period / 2)), int(round(period * 2))
    for t in range(lo, n):
        prev = np.arange(max(0, t - hi), t - lo + 1)
        if prev.size == 0:
            continue
        penalty = -tightness * np.log((t - prev) / period) ** 2
        cand = score[prev] + penalty
        k = int(np.argmax(cand))
        if cand[k] > 0:
            score[t] = o[t] + cand[k]
            back[t] = prev[k]
    # point de départ : le meilleur score dans la dernière période
    tail = np.arange(max(0, n - int(period)), n)
    t = int(tail[np.argmax(score[tail])])
    beats = []
    while t >= 0:
        beats.append(t)
        t = back[t]
    beats = np.array(beats[::-1])
    # enlève les beats « inventés » dans le silence au début/à la fin
    if beats.size:
        strong = onset[beats] > 0.1 * np.median(onset[beats] + 1e-9)
        if strong.any():
            first, last = np.argmax(strong), len(strong) - 1 - np.argmax(strong[::-1])
            beats = beats[first:last + 1]
    return beats


# ------------------------------------------------------------- paroles ----

def _plain(text):
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


_TAG = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\]")
_WORD = re.compile(r"<(\d+):(\d+(?:[.:]\d+)?)>\s*([^<]*)")


def _secs(m, s):
    return int(m) * 60 + float(s.replace(":", "."))


def parse_lrc(text, duration=None):
    """Paroles .lrc -> liste (temps, mot). Gère les lignes [mm:ss.xx] et les mots <mm:ss.xx>."""
    lines = []
    for raw in text.splitlines():
        tags = _TAG.findall(raw)
        if not tags:
            continue
        body = _TAG.sub("", raw).strip()
        for m, s in tags:
            lines.append((_secs(m, s), body))
    lines.sort(key=lambda x: x[0])
    words = []
    for i, (t, body) in enumerate(lines):
        if not body:
            continue
        timed = _WORD.findall(body)
        if timed:                                         # karaoké : chaque mot a son temps
            for m, s, w in timed:
                for k, part in enumerate(w.split()):
                    words.append((_secs(m, s) + 0.05 * k, part))
            continue
        tokens = body.split()
        end = lines[i + 1][0] if i + 1 < len(lines) else (duration or t + 0.4 * len(tokens))
        step = min(0.4, max(0.12, (end - t) / max(len(tokens), 1)))   # ~ débit de chant
        words += [(t + k * step, w) for k, w in enumerate(tokens)]
    return words


def find_keywords(words, keywords):
    keys = {_plain(k).strip(" ,.;!?'\"") for k in keywords if k.strip()}
    hits = []
    for t, w in words:
        clean = re.sub(r"[^\w]", "", _plain(w))
        if clean and clean in keys:
            hits.append((t, w))
    return hits


# ------------------------------------------------------------ analyse ----

def analyze(y, lrc_text=None, keywords=(), forced_tempo=None):
    """y : audio mono à SR Hz. forced_tempo : BPM imposé (bouton ×2 / ÷2 de l'onglet)."""
    duration = len(y) / SR
    spec, centers = band_spectrogram(y)
    onset = _normalize(_smooth(_flux(spec), 3))
    low = _normalize(_flux(spec, (centers >= 30) & (centers < 150)))
    mid = _normalize(_flux(spec, (centers >= 150) & (centers < 2500)))
    rms = np.sqrt(np.mean(np.square(_pad(y)[_frames(y)[1]]), axis=1)) if len(y) else np.zeros(1)

    body = _normalize(_flux(spec, centers < 5000))       # sans les cymbales/charlestons
    strong = np.array(_peaks(body, 0.3, 3))
    base = estimate_tempo(onset)
    if forced_tempo:                                      # tempo corrigé à la main (×2 / ÷2)
        tempo, frames = float(forced_tempo), track_beats(onset, float(forced_tempo))
    else:
        # T, 2T ou T/2 ? On garde, dans la plage la plus courante (85-175 BPM), celui dont
        # la grille couvre le mieux les vrais coups de batterie.
        best = None
        for cand in (base / 2, base, base * 2):
            if not 55 <= cand <= 210:
                continue
            fr = track_beats(onset, cand)
            cover = np.mean([np.min(np.abs(fr - p)) <= 2 for p in strong]) if len(strong) and len(fr) else 0
            in_range = 85 <= cand <= 175
            key = (in_range, cover if in_range else -abs(np.log2(cand / 120)))
            if best is None or key > best[0]:
                best = (key, cand, fr)
        tempo, frames = best[1], best[2]
    if len(frames) > 8:                                   # tempo réel d'après la grille obtenue
        tempo = float(60 / (np.median(np.diff(frames)) * DT))

    def around(x, f, w=2):
        return float(x[max(0, f - w):f + w + 1].max())

    strengths = [around(onset, f) for f in frames]
    lows = [around(low, f) for f in frames]
    mids = [around(mid, f) for f in frames]
    nb = len(frames)
    edges = list(frames) + [len(rms)]
    beat_energy = np.array([rms[edges[i]:max(edges[i] + 1, edges[i + 1])].mean() for i in range(nb)]) if nb else np.zeros(0)
    energy = _normalize(beat_energy) if nb else beat_energy

    # drops : beat où l'énergie des 4 beats suivants dépasse nettement celle des 8 précédents
    drops = []
    med = float(np.median(beat_energy)) if nb else 0
    jumps = np.zeros(nb)
    for i in range(8, nb - 3):
        before = beat_energy[i - 8:i].mean()
        after = beat_energy[i:i + 4].mean()
        if after > med and before > 0:
            jumps[i] = after / before
    for i in np.argsort(-jumps):
        if jumps[i] < 1.6:
            break
        if all(abs(i - d) >= 32 for d in drops):
            drops.append(int(i))

    # temps forts : calés sur le drop s'il y en a un (un drop tombe sur le « 1 »),
    # sinon la phase (0..3) où la grosse caisse tape le plus
    if drops:
        phase = drops[0] % 4
    else:
        phase = int(np.argmax([sum(lows[p::4]) for p in range(4)])) if nb >= 8 else 0
    beats = [Beat(t=float(frames[i] * DT + ONSET_LAG), strength=strengths[i], low=lows[i], mid=mids[i],
                  energy=float(energy[i]), bar_pos=(i - phase) % 4, drop=i in drops) for i in range(nb)]

    # attaques de voix/mélodie : partie harmonique (médiane dans le temps) entre 300 et 3400 Hz
    vocal = []
    if spec.shape[0] > 20:
        w = 9
        pt = np.pad(spec, ((w // 2, w // 2), (0, 0)), mode="edge")
        harm = np.median(np.lib.stride_tricks.sliding_window_view(pt, w, axis=0), axis=-1)
        pf = np.pad(spec, ((0, 0), (w // 2, w // 2)), mode="edge")
        perc = np.median(np.lib.stride_tricks.sliding_window_view(pf, w, axis=1), axis=-1)
        tonal = spec * (harm > perc)                        # ne garde que les sons « tenus »
        band = (centers >= 200) & (centers < 3400)
        vflux = _normalize(_smooth(_flux(tonal, band), 3))
        thr = float(np.mean(vflux) + 2.0 * np.std(vflux))
        vocal = [float(i * DT + ONSET_LAG) for i in _peaks(vflux, thr, int(0.25 / DT))]

    words = parse_lrc(lrc_text, duration) if lrc_text else []
    hits = find_keywords(words, keywords) if keywords else []

    env_n = 1500
    if len(y):
        chunks = np.array_split(np.abs(y), min(env_n, len(y)))
        envelope = [round(float(c.max()), 3) for c in chunks]
    else:
        envelope = []
    return Analysis(duration=duration, tempo=round(tempo, 1), beats=beats, vocal_onsets=vocal,
                    lyric_words=words, keyword_hits=hits, envelope=envelope)

"""Morceau de test : 124 BPM, 8 mesures calmes puis DROP, mélodie (voix) sur certains temps."""
import numpy as np
SR = 22050
def make(bpm=124.0, bars_intro=8, bars_drop=8, sr=SR, seed=0):
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    total = (bars_intro + bars_drop) * 4 * beat + 1.0
    n = int(total * sr); y = np.zeros(n)
    t0 = 0.5
    def add(sig, t):
        i = int(t * sr); j = min(n, i + len(sig))
        if i < n: y[i:j] += sig[: j - i]
    tt = np.arange(int(0.25 * sr)) / sr
    kick = np.sin(2 * np.pi * (50 + 80 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 12)
    snare = rng.normal(0, 1, len(tt)) * np.exp(-tt * 25) * 0.6
    hat = rng.normal(0, 1, int(0.05 * sr)) * np.exp(-np.arange(int(0.05 * sr)) / sr * 80) * 0.15
    beats, downbeats, vocal = [], [], []
    for b in range((bars_intro + bars_drop) * 4):
        t = t0 + b * beat; beats.append(t)
        intro = b < bars_intro * 4
        g = 0.25 if intro else 1.0
        if b % 4 == 0: downbeats.append(t)
        if b % 2 == 0: add(kick * g, t)
        else: add(snare * g, t)
        add(hat * g, t + beat / 2)
        if b % 4 in (0, 3) and b % 8 < 4:                # « voix » : notes tenues
            f = 220 * 2 ** (rng.integers(0, 12) / 12)
            d = np.arange(int(beat * 0.9 * sr)) / sr
            note = (np.sin(2*np.pi*f*d) + 0.4*np.sin(4*np.pi*f*d)) * np.minimum(d/0.02, 1) * 0.25
            add(note, t + beat * 0.25); vocal.append(t + beat * 0.25)
    if True:                                              # nappe de fond plus forte au drop
        d = np.arange(n) / sr
        pad = 0.05 * np.sin(2*np.pi*110*d) * np.where(d > t0 + bars_intro*4*beat, 4, 1)
        y += pad
    y = y / np.abs(y).max() * 0.9
    drop = t0 + bars_intro * 4 * beat
    return y.astype(np.float32), dict(bpm=bpm, beats=beats, downbeats=downbeats, drop=drop, vocal=vocal)

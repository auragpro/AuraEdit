"""Tests de l'analyse musicale sur des morceaux de synthèse (tempo, beats, drop, paroles)."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core import music_analysis as ma  # noqa: E402
from synth_music import make  # noqa: E402


class AnalysisTests(unittest.TestCase):
    def check(self, bpm):
        y, truth = make(bpm=bpm, seed=bpm)
        a = ma.analyze(y)
        self.assertAlmostEqual(a.tempo, bpm, delta=bpm * 0.03)
        bt = np.array([b.t for b in a.beats])
        err = np.array([np.min(np.abs(bt - t)) for t in truth["beats"]])
        self.assertGreater((err < 0.05).mean(), 0.9)
        self.assertEqual(len(a.drops), 1)
        self.assertAlmostEqual(a.drops[0], truth["drop"], delta=0.06)
        drop_beat = next(b for b in a.beats if b.drop)
        self.assertEqual(drop_beat.bar_pos, 0)              # un drop tombe sur le « 1 »

    def test_124(self):
        self.check(124)

    def test_150(self):
        self.check(150)

    def test_95(self):
        self.check(95)

    def test_forced_tempo(self):
        y, _ = make(bpm=124, seed=1)
        a = ma.analyze(y, forced_tempo=62)
        self.assertLess(len(a.beats), 40)

    def test_lrc_and_keywords(self):
        lrc = "[00:01.00]Je tire BANG bang !\n[00:04.00]<00:04.00>et <00:04.50>ça <00:05.10>part"
        words = ma.parse_lrc(lrc, duration=10)
        self.assertEqual(words[0], (1.0, "Je"))
        self.assertIn((5.1, "part"), words)
        hits = ma.find_keywords(words, ["bang", "Ça"])
        self.assertEqual([w for _, w in hits], ["BANG", "bang", "ça"])

    def test_silence(self):
        a = ma.analyze(np.zeros(22050 * 3, dtype=np.float32))
        self.assertEqual(a.drops, [])


if __name__ == "__main__":
    unittest.main()

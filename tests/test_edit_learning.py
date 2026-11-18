"""Tests « apprendre d'un edit déjà fait » : faux edit fabriqué avec des sons connus."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core import audio, edit_learning as el, music_analysis as ma, sound_ai as sa  # noqa: E402
from synth_music import make  # noqa: E402

SR = 44100


def _sounds():
    rng = np.random.default_rng(5)
    t = np.arange(int(0.35 * SR)) / SR
    vandal = (rng.normal(0, 1, len(t)) * 0.5 + np.sin(2 * np.pi * 700 * t)) * np.exp(-t * 18) * 0.5
    sheriff = (np.sin(2 * np.pi * 1900 * t) + 0.5 * np.sin(2 * np.pi * 3100 * t)) * np.exp(-t * 10) * 0.45
    tw = np.arange(int(0.6 * SR)) / SR
    sweep = np.sin(2 * np.pi * (300 * tw + 2500 * tw ** 2))
    woosh = (rng.normal(0, 1, len(tw)) * 0.6 + sweep * 0.4) * (tw / tw[-1]) ** 2 * 0.5
    return {"Vandal/v1.wav": vandal, "Sheriff/s1.wav": sheriff, "Wooshs/swoosh.wav": woosh}


class EditLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        for name, x in _sounds().items():
            p = cls.dir / "lib" / name
            p.parent.mkdir(parents=True, exist_ok=True)
            audio.save_wav(p, x.astype(np.float32), SR)
        cls.lib = sa.scan_library(cls.dir / "lib")
        by = {s.category: s.path for s in cls.lib}
        y, _ = make(bpm=124, seed=7)
        cls.music = cls.dir / "musique.wav"
        audio.save_wav(cls.music, y, 22050)
        cls.analysis = ma.analyze(y)
        # style de l'edit : Vandal sur les temps forts, Sheriff sur le 3e temps, woosh vers le drop
        pls = []
        for b in cls.analysis.beats:
            if b.drop:
                pls.append(sa.Placement(t=b.t, category="woosh", sound=by["woosh"], ctx="", role=""))
            elif b.bar_pos == 0:
                pls.append(sa.Placement(t=b.t, category="vandal", sound=by["vandal"], ctx="", role=""))
            elif b.bar_pos == 2:
                pls.append(sa.Placement(t=b.t, category="sheriff", sound=by["sheriff"], ctx="", role=""))
        _, sfx = sa.render(cls.music, pls, music_gain=1.0)
        m44 = audio.load(cls.music, SR, 2)
        cut, intro = 3.0, 2.0                       # l'edit coupe 3 s de musique et ajoute 2 s d'intro
        full = m44 * 0.7 + sfx
        intro_sig = np.random.default_rng(1).normal(0, 0.05, (int(intro * SR), 2))
        edit = np.concatenate([intro_sig, full[int(cut * SR):]]).astype(np.float32)
        edit /= max(1.0, np.abs(edit).max() / 0.98)
        cls.edit = cls.dir / "edit.wav"
        audio.save_wav(cls.edit, edit, SR)
        cls.truth = [p for p in pls if p.t > cut + 0.2]
        cls.true_shift = intro - cut
        cls.example = el.listen(cls.edit, cls.music, cls.lib)

    def test_alignment(self):
        self.assertAlmostEqual(self.example.shift, self.true_shift, delta=0.01)
        self.assertAlmostEqual(self.example.start, 3.0, delta=0.5)

    def test_finds_sound_kills(self):
        dets = self.example.detections
        found = sum(1 for p in self.truth
                    if any(abs(d.t - p.t) < 0.05 and d.category == p.category for d in dets))
        self.assertGreaterEqual(found / len(self.truth), 0.85, f"{found}/{len(self.truth)}")
        false = [d for d in dets if not any(abs(d.t - p.t) < 0.05 for p in self.truth)]
        self.assertLessEqual(len(false), 2, false)

    def test_wrong_music_is_refused(self):
        y2, _ = make(bpm=150, seed=3)
        other = self.dir / "autre.wav"
        audio.save_wav(other, y2, 22050)
        with self.assertRaises(ValueError):
            el.listen(self.edit, other, self.lib)

    def test_needs_library(self):
        with self.assertRaises(ValueError):
            el.listen(self.edit, self.music, [])

    def test_ai_copies_the_style(self):
        ai = sa.SoundAI(path=self.dir / "modele.json")
        kept, empty = el.apply(ai, self.example)
        self.assertGreater(kept, 10)
        self.assertGreater(empty, 5)
        # ce que l'IA propose maintenant sur une autre musique
        other = ma.analyze(make(bpm=140, seed=21)[0])
        good = total = 0
        for seed in range(10):
            for p in ai.generate(other, self.lib, density=0.5, creativity=0.2, seed=seed):
                total += 1
                if p.role == "temps_fort":
                    good += p.category == "vandal"
                elif p.role == "caisse_claire":
                    good += 0                          # l'edit n'en met jamais sur la caisse claire
                else:
                    good += 1
        self.assertGreater(total, 0)
        self.assertGreaterEqual(good / total, 0.75)
        snare = sum(1 for seed in range(10) for p in ai.generate(other, self.lib, seed=seed)
                    if p.role == "caisse_claire")
        self.assertLess(snare, 10)
        # sauvegardé sur le disque
        again = sa.SoundAI(path=self.dir / "modele.json")
        self.assertEqual(again.decisions, ai.decisions)


if __name__ == "__main__":
    unittest.main()

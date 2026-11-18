"""Tests de l'IA des sons : génération, apprentissage, sauvegarde, rendu."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core import audio, music_analysis as ma, sound_ai as sa  # noqa: E402
from synth_music import make  # noqa: E402

SR = 44100


def _write(path, x):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    audio.save_wav(path, x, SR)


class SoundAITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        t = np.arange(int(0.3 * SR)) / SR
        shot = np.sin(2 * np.pi * 900 * t) * np.exp(-t * 15) * 0.6
        for name in ("Vandal/v1.wav", "Vandal/v2.wav", "Sheriff/s1.wav", "Wooshs/swoosh.wav", "Impacts/boom.wav"):
            _write(cls.dir / "lib" / name, shot)
        cls.lib = sa.scan_library(cls.dir / "lib")
        cls.songs = [ma.analyze(make(bpm=b, seed=b)[0]) for b in (124, 140)]

    def ai(self):
        return sa.SoundAI(path=self.dir / f"m{np.random.randint(1e9)}.json")

    def test_categories(self):
        self.assertEqual(sa.library_summary(self.lib),
                         {"vandal": 2, "sheriff": 1, "woosh": 1, "impact": 1})
        self.assertEqual(sa.category_of("C:/sons/KILL Sherif 2.wav"), "sheriff")
        self.assertEqual(sa.category_of("x/whoosh_fast.mp3"), "woosh")

    def test_generate_has_drop_sound(self):
        pl = self.ai().generate(self.songs[0], self.lib, seed=1)
        self.assertTrue(pl)
        drop = self.songs[0].drops[0]
        self.assertTrue(any(abs(p.t - drop) < 0.01 for p in pl))

    def test_learning_follows_taste(self):
        taste = {"temps_fort": "sheriff", "caisse_claire": None, "grosse_caisse": None,
                 "contre_temps": None, "voix": None, "drop": "impact", "avant_drop": "woosh"}
        ai = self.ai()
        by = {}
        for s in self.lib:
            by.setdefault(s.category, []).append(s)

        def score(pl):
            ok = sum(1 for p in pl if taste.get(p.role) == p.category)
            return ok / max(1, len(pl))

        first = score(ai.generate(self.songs[0], self.lib, seed=0))
        for it in range(10):
            pl = ai.generate(self.songs[it % 2], self.lib, seed=it)
            for p in list(pl):
                want = taste.get(p.role)
                if want is None:
                    ai.learn_delete(p)
                    pl.remove(p)
                elif want != p.category:
                    ai.learn_change(p, want, by[want][0].path)
                    p.category = want
            for p in pl:
                ai.learn_keep(p)
        last = score(ai.generate(self.songs[0], self.lib, seed=99))
        self.assertGreater(last, first)
        self.assertGreater(last, 0.75)
        ai.save()
        self.assertEqual(sa.SoundAI(path=ai.path).decisions, ai.decisions)

    def test_render_alignment(self):
        y, _ = make(bpm=124, seed=5)
        music = self.dir / "music.wav"
        audio.save_wav(music, y, 22050)
        try:
            audio.ffmpeg_exe()
        except RuntimeError:
            self.skipTest("FFmpeg absent")
        p = sa.Placement(t=2.0, category="vandal", sound=self.lib[0].path, ctx="temps_fort|fort", role="temps_fort")
        mix, sfx = sa.render(music, [p], self.dir / "mix.wav", self.dir / "sfx.wav")
        env = np.abs(sfx).mean(1)
        start = np.argmax(env > 0.05) / SR
        self.assertAlmostEqual(start, 2.0, delta=0.005)
        self.assertTrue((self.dir / "mix.wav").exists())


if __name__ == "__main__":
    unittest.main()

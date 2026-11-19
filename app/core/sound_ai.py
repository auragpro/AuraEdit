"""IA des « sound kills » : place des sons sur la musique et apprend de tes choix.

Comment elle décide
-------------------
Chaque moment intéressant de la musique reçoit un CONTEXTE, par exemple
« drop|fort », « temps_fort|moyen », « voix|faible », « mot_cle ».
Pour chaque contexte, le modèle retient :
  - une probabilité de mettre un son (combien de fois tu as gardé / supprimé) ;
  - une préférence de catégorie (vandal, sheriff, woosh, impact...) ;
et pour chaque fichier son, une note (aimé / rejeté).

Comment elle apprend
--------------------
Garder un son, en supprimer un, en changer ou en ajouter un à la main :
chaque action met à jour ces compteurs (statistique bayésienne simple).
Plus tu l'utilises, plus ses propositions ressemblent à tes edits.
Le modèle est enregistré dans %APPDATA%/AuraEdit/sons_ia_modele.json.
"""
import json
import os
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from . import audio
from .project import config_dir

AUDIO_EXT = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac"}
OUT_SR = 44100

# catégorie -> mots qui la reconnaissent dans le nom du fichier ou du dossier
CATEGORIES = {
    "vandal": ("vandal",),
    "sheriff": ("sheriff", "sherif"),
    "phantom": ("phantom",),
    "operator": ("operator", "op_", "awp", "sniper"),
    "woosh": ("woosh", "whoosh", "swoosh", "swish", "wosh", "transition"),
    "impact": ("impact", "hit", "boom", "bass", "punch", "slam"),
    "riser": ("riser", "rise", "uplifter", "reverse", "sweep"),
}
LABELS = {"vandal": "Vandal", "sheriff": "Sheriff", "phantom": "Phantom", "operator": "Operator",
          "woosh": "Woosh", "impact": "Impact", "riser": "Riser", "autre": "Autre"}
COLORS = {"vandal": "#ff4655", "sheriff": "#f5a623", "phantom": "#b36bff", "operator": "#4aa8ff",
          "woosh": "#3ddc97", "impact": "#ffffff", "riser": "#00d1c1", "autre": "#8b978f"}
ALIGN_PEAK = {"woosh", "riser"}       # ces sons sont calés par leur pic (le « fffff » arrive sur le beat)

ROLES = {"drop": "Drop", "avant_drop": "Avant le drop", "temps_fort": "Temps fort",
         "caisse_claire": "Caisse claire", "grosse_caisse": "Grosse caisse",
         "contre_temps": "Contre-temps", "voix": "Voix", "mot_cle": "Mot-clé"}

# a priori (avant tout entraînement) : [gardé, supprimé]
PRIOR_PLACE = {"drop": (9, 1), "avant_drop": (6, 2), "temps_fort": (3, 3), "caisse_claire": (2, 4),
               "grosse_caisse": (1, 5), "contre_temps": (1, 12), "voix": (2, 5), "mot_cle": (8, 1)}
ENERGY_BONUS = {"fort": 2.0, "moyen": 0.5, "faible": -0.5}
PRIOR_CAT = {
    "drop": {"impact": 3, "vandal": 2, "sheriff": 1},
    "avant_drop": {"woosh": 4, "riser": 3},
    "temps_fort": {"vandal": 3, "sheriff": 2, "impact": 1},
    "caisse_claire": {"sheriff": 3, "vandal": 2},
    "grosse_caisse": {"vandal": 2, "impact": 2},
    "contre_temps": {"sheriff": 1, "woosh": 1},
    "voix": {"woosh": 3, "sheriff": 1},
    "mot_cle": {"vandal": 3, "sheriff": 3, "phantom": 2},
}
BASE_GAIN = {"woosh": 0.7, "riser": 0.7, "impact": 1.0}


# ---------------------------------------------------------- bibliothèque ----

@dataclass
class Sound:
    path: str
    category: str

    @property
    def key(self):                       # survit à un déplacement du dossier
        return f"{self.category}/{Path(self.path).name.lower()}"

    @property
    def name(self):
        return Path(self.path).name


def category_of(path, root=None):
    rel = str(Path(path).relative_to(root)) if root else str(path)
    low = rel.lower().replace("\\", "/")
    for cat, words in CATEGORIES.items():
        if any(w in low for w in words):
            return cat
    return "autre"


def scan_library(folder, limit=3000):
    folder = Path(folder)
    sounds = []
    for dirpath, dirnames, files in os.walk(folder):
        dirnames.sort()                                   # même ordre sur Windows et ailleurs
        for f in sorted(files):
            if Path(f).suffix.lower() in AUDIO_EXT:
                p = Path(dirpath) / f
                sounds.append(Sound(str(p), category_of(p, folder)))
                if len(sounds) >= limit:
                    return sounds
    return sounds


def library_summary(sounds):
    out = {}
    for s in sounds:
        out[s.category] = out.get(s.category, 0) + 1
    return out


# ------------------------------------------------------------ contextes ----

@dataclass
class Moment:
    t: float
    role: str
    energy: str          # "faible" / "moyen" / "fort"
    weight: float        # force musicale (0..1)

    @property
    def ctx(self):
        return self.role if self.role == "mot_cle" else f"{self.role}|{self.energy}"


def _energy_label(e):
    return "fort" if e >= 0.66 else "moyen" if e >= 0.33 else "faible"


def moments(analysis, use_drops=True, use_beats=True, use_voice=True, use_keywords=True):
    """Liste des moments candidats (un beat = un seul rôle, le plus important)."""
    out = []
    beats = analysis.beats
    for i, b in enumerate(beats):
        e = _energy_label(b.energy)
        if b.drop:
            if use_drops:
                out.append(Moment(b.t, "drop", e, 1.0))
                out.append(Moment(b.t, "avant_drop", e, 0.9))   # woosh/riser dont le pic tombe sur le drop
            continue
        if not use_beats:
            continue
        if b.bar_pos == 0:
            role = "temps_fort"
        elif b.mid > 0.5 and b.bar_pos in (1, 3):
            role = "caisse_claire"
        elif b.low > 0.5:
            role = "grosse_caisse"
        else:
            role = "contre_temps"
        out.append(Moment(b.t, role, e, float(b.strength)))
    if use_voice:
        bt = np.array([b.t for b in beats]) if beats else np.zeros(0)
        for t in analysis.vocal_onsets:
            if bt.size and np.min(np.abs(bt - t)) < 0.12:
                continue                                  # déjà couvert par un beat
            e = _energy_label(_energy_at(beats, t))
            out.append(Moment(t, "voix", e, 0.5))
    if use_keywords:
        out += [Moment(t, "mot_cle", "fort", 1.0) for t, _ in analysis.keyword_hits]
    out.sort(key=lambda m: (m.t, m.role))
    return out


def _energy_at(beats, t):
    if not beats:
        return 0.5
    i = int(np.argmin([abs(b.t - t) for b in beats]))
    return beats[i].energy


def context_at(analysis, t, max_dist=0.15):
    """Contexte musical d'un instant (pour apprendre d'un son ajouté à la main)."""
    cands = moments(analysis)
    if cands:
        m = min(cands, key=lambda c: abs(c.t - t))
        if abs(m.t - t) <= max_dist and m.role != "avant_drop":
            return m.ctx, m.role
    return f"contre_temps|{_energy_label(_energy_at(analysis.beats, t))}", "contre_temps"


# --------------------------------------------------------------- modèle ----

@dataclass
class Placement:
    t: float
    category: str
    sound: str
    ctx: str
    role: str
    gain: float = 1.0
    origin: str = "ia"            # "ia" ou "manuel"
    learned: bool = False         # déjà pris en compte par l'apprentissage
    id: int = field(default_factory=lambda: random.getrandbits(31))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in keys})


class SoundAI:
    def __init__(self, path=None):
        self.path = Path(path) if path else config_dir() / "sons_ia_modele.json"
        self.place = {}       # ctx -> [gardé, supprimé] appris
        self.cat = {}         # ctx -> {catégorie: poids appris}
        self.sound = {}       # clé son -> [aimé, rejeté]
        self.decisions = 0
        self.load()

    # ---------------------------------------------------- sauvegarde
    def load(self):
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            self.place = {k: list(v) for k, v in d.get("place", {}).items()}
            self.cat = {k: dict(v) for k, v in d.get("cat", {}).items()}
            self.sound = {k: list(v) for k, v in d.get("sound", {}).items()}
            self.decisions = int(d.get("decisions", 0))
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def save(self):
        data = {"version": 1, "place": self.place, "cat": self.cat, "sound": self.sound,
                "decisions": self.decisions}
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def reset(self):
        self.place, self.cat, self.sound, self.decisions = {}, {}, {}, 0
        self.save()

    # ---------------------------------------------------- probabilités
    def p_place(self, ctx):
        role, _, energy = ctx.partition("|")
        a, b = PRIOR_PLACE.get(role, (1, 5))
        a = max(0.2, a + ENERGY_BONUS.get(energy, 0))
        la, lb = self.place.get(ctx, (0, 0))
        return (a + la) / (a + b + la + lb)

    def cat_weights(self, ctx, available):
        role = ctx.partition("|")[0]
        prior = PRIOR_CAT.get(role, {})
        learned = self.cat.get(ctx, {})
        return {c: 0.3 + prior.get(c, 0) + learned.get(c, 0) for c in available}

    def sound_score(self, s):
        """Poids d'un son : un son que tu utilises souvent (ou gardes) passe devant ceux
        que tu n'as jamais pris ; un son supprimé passe derrière."""
        a, b = self.sound.get(s.key, (0, 0))
        return (a + 0.5) / (b + 1.0)

    # ---------------------------------------------------- génération
    def generate(self, analysis, library, density=0.5, creativity=0.3, seed=None,
                 use_drops=True, use_beats=True, use_voice=True, use_keywords=True):
        if not library:
            raise ValueError("Ta bibliothèque de sons est vide.")
        rng = random.Random(seed)
        by_cat = {}
        for s in library:
            by_cat.setdefault(s.category, []).append(s)
        available = list(by_cat)
        temp = 0.25 + 1.5 * creativity                    # « température » des choix
        sharp = 2 + (1 - creativity) * 18                 # créativité basse = décisions nettes
        out, last_t, last_sound = [], -9.0, None
        for m in moments(analysis, use_drops, use_beats, use_voice, use_keywords):
            p = min(1.0, self.p_place(m.ctx) * density * 2)
            p_eff = 1 / (1 + np.exp(-(p - 0.5) * sharp))
            if rng.random() >= p_eff:
                continue
            if m.t - last_t < 0.18 and m.role not in ("avant_drop",):
                continue                                  # pas deux sons collés
            weights = self.cat_weights(m.ctx, available)
            if m.role == "avant_drop":                    # seulement des sons qui « montent »
                weights = {c: w for c, w in weights.items() if c in ALIGN_PEAK} or {}
                if not weights:
                    continue
            cat = _pick(rng, weights, temp)
            pool = by_cat[cat]
            snd_w = {i: self.sound_score(s) for i, s in enumerate(pool)}
            if len(pool) > 1 and last_sound is not None:
                for i, s in enumerate(pool):              # évite de répéter le même fichier
                    if s.path == last_sound:
                        snd_w[i] *= 0.3
            snd = pool[_pick(rng, snd_w, temp)]
            gain = BASE_GAIN.get(cat, 0.9) * (0.75 + 0.25 * m.weight)
            out.append(Placement(t=round(m.t, 3), category=cat, sound=snd.path, ctx=m.ctx,
                                 role=m.role, gain=round(gain, 2)))
            if m.role != "avant_drop":
                last_t = m.t
            last_sound = snd.path
        return out

    # ---------------------------------------------------- apprentissage
    def _bump_place(self, ctx, kept, w=1.0):
        a, b = self.place.get(ctx, [0, 0])
        self.place[ctx] = [a + (w if kept else 0), b + (0 if kept else w)]

    def _bump_cat(self, ctx, cat, w=1.0):
        d = self.cat.setdefault(ctx, {})
        d[cat] = max(-0.25, d.get(cat, 0) + w)

    def _bump_sound(self, key, liked, w=1.0):
        a, b = self.sound.get(key, [0, 0])
        self.sound[key] = [a + (w if liked else 0), b + (0 if liked else w)]

    @staticmethod
    def _key(category, path):
        return f"{category}/{Path(path).name.lower()}"

    def learn_keep(self, p):
        """Le son a été gardé (validation de l'edit)."""
        if p.learned:
            return
        self._bump_place(p.ctx, True)
        self._bump_cat(p.ctx, p.category)
        self._bump_sound(self._key(p.category, p.sound), True)
        p.learned = True
        self.decisions += 1

    def learn_delete(self, p):
        """Le son proposé a été supprimé : moins de sons dans ce contexte."""
        if p.origin == "ia":
            self._bump_place(p.ctx, False)
            self._bump_sound(self._key(p.category, p.sound), False, 0.5)
            self.decisions += 1

    def learn_change(self, p, new_category, new_sound):
        """Un son remplacé par un autre : ce fichier/cette catégorie plaisent moins."""
        self._bump_sound(self._key(p.category, p.sound), False)
        self._bump_sound(self._key(new_category, new_sound), True)
        if new_category != p.category:
            self._bump_cat(p.ctx, p.category, -0.5)
        self._bump_cat(p.ctx, new_category)
        self.decisions += 1

    def learn_add(self, ctx, category, sound):
        """Un son ajouté à la main : l'IA aurait dû en mettre un ici."""
        self._bump_place(ctx, True)
        self._bump_cat(ctx, category)
        self._bump_sound(self._key(category, sound), True)
        self.decisions += 1

    def level(self):
        """Niveau d'entraînement lisible."""
        n = self.decisions
        if n == 0:
            return "Pas encore entraînée (réglages de départ)"
        if n < 30:
            return f"Débutante ({n} choix appris)"
        if n < 150:
            return f"En progrès ({n} choix appris)"
        return f"Bien entraînée ({n} choix appris)"


def _pick(rng, weights, temp):
    keys = list(weights)
    w = np.array([max(1e-6, weights[k]) for k in keys], dtype=float) ** (1 / max(temp, 1e-3))
    w /= w.sum()
    return keys[int(np.searchsorted(np.cumsum(w), rng.random() * 0.999999))]


# ------------------------------------------------------------- rendu ----

class SoundCache:
    def __init__(self):
        self._c = {}

    def get(self, path):
        if path not in self._c:
            x = audio.load(path, OUT_SR, channels=2)
            mono = np.abs(x).mean(1)
            peak = float(mono.max()) or 1.0
            onset = int(np.argmax(mono > 0.1 * peak))
            k = max(1, int(0.01 * OUT_SR))
            env = np.convolve(mono, np.ones(k) / k, mode="same")
            self._c[path] = (x, onset, int(np.argmax(env)))
        return self._c[path]


def render(music_path, placements, out_mix=None, out_sfx=None, cache=None, music_gain=0.85):
    """Mixe la musique et les sons. Renvoie (mix, sfx) en stéréo 44,1 kHz."""
    cache = cache or SoundCache()
    music = audio.load(music_path, OUT_SR, channels=2) * music_gain
    sfx = np.zeros_like(music)
    n = len(music)
    for p in placements:
        try:
            x, onset, peak = cache.get(p.sound)
        except RuntimeError:
            continue                                      # fichier son illisible/supprimé : ignoré
        anchor = peak if p.category in ALIGN_PEAK else onset
        start = int(round(p.t * OUT_SR)) - anchor
        a, b = max(0, start), min(n, start + len(x))
        if b > a:
            sfx[a:b] += x[a - start:b - start] * p.gain
    mix = music + sfx
    for arr in (mix, sfx):                                # évite la saturation
        m = float(np.abs(arr).max()) if arr.size else 0
        if m > 0.99:
            arr *= 0.99 / m
    if out_mix:
        audio.save_wav(out_mix, mix, OUT_SR)
    if out_sfx:
        audio.save_wav(out_sfx, sfx, OUT_SR)
    return mix, sfx

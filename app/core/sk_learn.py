"""Reconnaître le type d'un sound kill (clip / flickaway, dash, kunai) et apprendre des corrections.

Pour chaque sound kill on regarde, dans l'ordre :
  1. ce que tu as déjà dit pour ce même son (même fichier sample) ;
  2. le nom du son (« dash », « kunai », « flick »...) ;
  3. les sound kills que tu as déjà classés qui lui ressemblent (rythme + empreinte du son) ;
  4. le rythme : un sound kill très rapproché des autres = moment rapide = dash.
Sinon : inconnu (« ? »), c'est toi qui choisis.
Chaque validation / correction est enregistrée et sert aux suivantes.
"""
import json
import math
from pathlib import Path

import numpy as np

from . import audio
from .markers import SR, TYPES, _profile

FAST = 0.30            # secondes : en dessous, c'est un moment rapide (dash)
MAX_EXAMPLES = 3000
_PROFILES = {}


def _file():
    from .project import config_dir
    return config_dir() / "apprentissage_soundkills.json"


def load():
    try:
        d = json.loads(_file().read_text(encoding="utf-8"))
        if isinstance(d, dict):
            d.setdefault("samples", {})
            d.setdefault("exemples", [])
            return d
    except (OSError, ValueError):
        pass
    return {"samples": {}, "exemples": []}


def save(d):
    d["exemples"] = d["exemples"][-MAX_EXAMPLES:]
    try:
        _file().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def key(sample):
    return Path((sample or "").replace("\\", "/")).name.lower()


def profile(sample):
    """Empreinte du son (24 bandes), si le fichier est sur le PC."""
    k = key(sample)
    if k in _PROFILES:
        return _PROFILES[k]
    p = None
    try:
        f = Path(sample)
        if f.is_file():
            y = audio.load(str(f), SR, 1)[: int(0.4 * SR)]
            if len(y) > 512:
                p = [round(float(v), 4) for v in _profile(y)]
    except Exception:
        p = None
    _PROFILES[k] = p
    return p


def features(hits):
    """Rythme de chaque sound kill : écart avec le précédent / le suivant, durée."""
    out = []
    for i, h in enumerate(hits):
        prev = h["t"] - hits[i - 1]["t"] if i > 0 else 9.0
        nxt = hits[i + 1]["t"] - h["t"] if i + 1 < len(hits) else 9.0
        out.append([round(min(prev, 9.0), 3), round(min(nxt, 9.0), 3), round(min(h.get("fin", h["t"]) - h["t"], 9.0), 3)])
    return out


def _by_name(text):
    low = (text or "").lower()
    if "dash" in low or "dsh" in low:
        return "dash"
    if "kunai" in low:
        return "kunai"
    if "flick" in low or "knife" in low or "couteau" in low:
        return "clip"
    return None


def _dist(f1, p1, f2, p2):
    d = sum((math.log(a + 0.05) - math.log(b + 0.05)) ** 2 for a, b in zip(f1, f2)) / 3
    if p1 and p2:
        d += 2.0 * (1.0 - float(np.dot(p1, p2)))
    else:
        d += 0.3
    return d


def predict(hits, model=None):
    """-> liste de (type ou None, confiance 0-1, raison) pour chaque sound kill."""
    model = model or load()
    feats = features(hits)
    ex_all = model["exemples"]
    out = []
    for h, f in zip(hits, feats):
        k = key(h["sample"])
        counts = model["samples"].get(k)
        if counts:
            best = max(counts, key=counts.get)
            tot = sum(counts.values())
            if counts[best] / tot >= 0.6:
                # même son mais rythme très rapide : le rythme l'emporte si tu l'as déjà vu en dash
                if min(f[0], f[1]) < FAST and counts.get("dash"):
                    out.append(("dash", 0.9, "même son, moment rapide"))
                else:
                    out.append((best, min(0.99, 0.6 + 0.1 * tot), "tu as déjà classé ce son"))
                continue
        name = _by_name(h.get("nom", "") + " " + k)
        if name:
            out.append((name, 0.8, "d'après le nom du son"))
            continue
        ex = [e for e in ex_all if e.get("f")]
        if ex:
            p = profile(h["sample"])
            near = sorted(ex, key=lambda e: _dist(f, p, e["f"], e.get("p")))[:5]
            votes = {}
            for e in near:
                w = 1.0 / (0.05 + _dist(f, p, e["f"], e.get("p")))
                votes[e["type"]] = votes.get(e["type"], 0) + w
            best = max(votes, key=votes.get)
            conf = votes[best] / sum(votes.values())
            if conf >= 0.6 and _dist(f, p, near[0]["f"], near[0].get("p")) < 0.8:
                out.append((best, round(conf * 0.85, 2), "ressemble à tes sound kills déjà classés"))
                continue
        if min(f[0], f[1]) < FAST:
            out.append(("dash", 0.6, "moment rapide"))
            continue
        out.append((None, 0.0, "inconnu"))
    return out


def learn(hits, types, model=None):
    """Enregistre tes choix (validation ou correction) pour les prochaines fois."""
    model = model or load()
    feats = features(hits)
    for h, f, t in zip(hits, feats, types):
        if t not in TYPES:
            continue
        k = key(h["sample"])
        c = model["samples"].setdefault(k, {})
        c[t] = c.get(t, 0) + 1
        model["exemples"].append({"f": f, "p": profile(h["sample"]), "type": t, "s": k})
    save(model)
    return model


def correct(marker, new_type):
    """Correction faite plus tard sur la frise (un repère venu d'un .flp garde son son et son rythme)."""
    src = marker.get("src")
    if not src or new_type not in TYPES:
        return
    model = load()
    k = key(src.get("sample"))
    c = model["samples"].setdefault(k, {})
    old = src.get("type")
    if old in c and c[old] > 0:
        c[old] -= 1                             # on retire l'ancien choix
    c[new_type] = c.get(new_type, 0) + 2        # une correction compte double
    model["exemples"].append({"f": src.get("f"), "p": profile(src.get("sample")), "type": new_type, "s": k})
    src["type"] = new_type
    save(model)


def stats():
    m = load()
    return len(m["samples"]), len(m["exemples"])

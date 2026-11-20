"""Clips « virtuels » : un morceau d'une vidéo existante (ex. un dash d'une compilation), sans créer
de nouveau fichier sur le PC. Le chemin d'un clip virtuel est une simple chaîne :

    <vidéo source>|<nom>|<début s>|<fin s>

« | » est interdit dans les noms de fichiers Windows, donc aucun vrai fichier ne peut ressembler à ça.
Partout où l'app lit une vidéo avec FFmpeg, elle passe par input_args() qui lit seulement ce morceau,
à la frame exacte."""
from pathlib import Path

SEP = "|"
EPS = 0.001          # 1 ms avant la 1re frame : FFmpeg démarre pile sur elle (même à 240 i/s)


def make(src, name, start, end):
    return f"{Path(src)}{SEP}{name}{SEP}{start:.6f}{SEP}{end:.6f}"


def parse(p):
    """(source, nom, début, fin) pour un clip virtuel, sinon None."""
    if p is None:
        return None
    parts = str(p).split(SEP)
    if len(parts) != 4:
        return None
    try:
        return parts[0], parts[1], float(parts[2]), float(parts[3])
    except ValueError:
        return None


def is_virtual(p):
    return parse(p) is not None


def source(p):
    v = parse(p)
    return v[0] if v else str(p)


def exists(p):
    return bool(p) and Path(source(p)).is_file()


def name(p):
    v = parse(p)
    return v[1] if v else Path(str(p)).name


def stem(p):
    v = parse(p)
    return v[1] if v else Path(str(p)).stem


def offset(p):
    v = parse(p)
    return v[2] if v else 0.0


def length(p):
    """Durée du morceau (None pour un vrai fichier)."""
    v = parse(p)
    return (v[3] - v[2]) if v else None


def input_args(p, ss=None, t=None):
    """Arguments FFmpeg pour lire le clip p à partir de ss secondes (dans le clip), pendant t secondes.
    Pour un vrai fichier : [-ss ss] [-t t] -i p. Pour un clip virtuel : seulement son morceau."""
    v = parse(p)
    if not v:
        out = []
        if ss is not None:
            out += ["-ss", f"{max(0.0, ss):.6f}"]
        if t is not None:
            out += ["-t", f"{max(0.01, t):.6f}"]
        return out + ["-i", str(p)]
    src, _, a, b = v
    s = max(0.0, ss or 0.0)
    dur = max(0.01, (b - a) - s)
    if t is not None:
        dur = min(dur, max(0.01, t))
    return ["-ss", f"{max(0.0, a + s - EPS):.6f}", "-t", f"{dur:.6f}", "-i", src]

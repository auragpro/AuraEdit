"""Un « projet » = un edit en cours : intro, musique, clips, kunais, outro.

Chaque projet est sauvegardé automatiquement en JSON dans
    Documents/AuraEdit/Projets/<nom>.auraedit
et la liste des derniers projets est gardée dans
    %APPDATA%/AuraEdit/recents.json   (Windows)
"""
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
KUNAI_POSITIONS = ("gauche", "droite", "les deux")
MAX_RECENTS = 8


# ------------------------------------------------------------- dossiers ----

def config_dir():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    d = base / "AuraEdit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def projects_dir():
    d = Path(os.environ.get("AURAEDIT_PROJECTS") or Path.home() / "Documents" / "AuraEdit" / "Projets")
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------- projet ----

@dataclass
class KunaiSettings:
    enabled: bool = True
    position: str = "les deux"                  # "gauche", "droite" ou "les deux"
    videos: list[str] = field(default_factory=list)   # vidéos de kills avec Jett


def default_sons():
    """Réglages de l'onglet Sons IA."""
    return {"dossier": None, "paroles": None, "mots_cles": "", "densite": 0.5, "creativite": 0.3,
            "drops": True, "temps": True, "voix": True, "tempo_force": None, "placements": []}


@dataclass
class Project:
    name: str
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    intro: str | None = None
    outro: str | None = None
    music: str | None = None
    clips: list[str] = field(default_factory=list)     # dans l'ordre de l'edit
    kunai: KunaiSettings = field(default_factory=KunaiSettings)
    sons: dict = field(default_factory=default_sons)
    path: str | None = None                             # fichier .auraedit (non sauvegardé dedans)

    @classmethod
    def new(cls):
        name = "Edit du " + datetime.now().strftime("%d-%m-%Y %Hh%M")
        p = cls(name=name)
        base = re.sub(r'[<>:"/\\|?*]', "_", name)
        target = projects_dir() / f"{base}.auraedit"
        n = 2
        while target.exists():
            target = projects_dir() / f"{base} ({n}).auraedit"
            n += 1
        p.path = str(target)
        p.save()
        return p

    # -- sauvegarde
    def to_dict(self):
        d = asdict(self)
        d.pop("path")
        d["format"] = 1
        return d

    def save(self):
        if not self.path:
            raise ValueError("Projet sans emplacement")
        target = Path(self.path)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)      # écriture atomique : pas de projet à moitié écrit
        add_recent(target)

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        kunai = data.get("kunai") or {}
        pos = kunai.get("position")
        p = cls(
            name=str(data.get("name") or Path(path).stem),
            created=str(data.get("created") or ""),
            intro=data.get("intro"),
            outro=data.get("outro"),
            music=data.get("music"),
            clips=[str(c) for c in data.get("clips") or []],
            kunai=KunaiSettings(enabled=bool(kunai.get("enabled", True)),
                                position=pos if pos in KUNAI_POSITIONS else "les deux",
                                videos=[str(v) for v in kunai.get("videos") or []]),
            sons={**default_sons(), **(data.get("sons") if isinstance(data.get("sons"), dict) else {})},
            path=str(path),
        )
        if not isinstance(p.sons.get("placements"), list):
            p.sons["placements"] = []
        add_recent(path)
        return p

    # -- état
    def missing_files(self):
        """Fichiers du projet qui n'existent plus sur le PC (déplacés, supprimés...)."""
        files = [self.intro, self.outro, self.music, *self.clips, *self.kunai.videos, self.sons.get("paroles")]
        return [f for f in files if f and not Path(f).is_file()]

    def checklist(self):
        """Ce qui est prêt / ce qui manque, pour l'onglet Accueil."""
        return [
            ("Intro", bool(self.intro)),
            ("Musique", bool(self.music)),
            (f"Clips ({len(self.clips)})", bool(self.clips)),
            ("Kunais Jett", (not self.kunai.enabled) or bool(self.kunai.videos)),
            (f"Sons IA ({len(self.sons.get('placements', []))})", bool(self.sons.get("placements"))),
        ]


# -------------------------------------------------------- récents ----

def _recents_file():
    return config_dir() / "recents.json"


def load_recents():
    """Derniers projets qui existent encore, du plus récent au plus ancien."""
    try:
        items = json.loads(_recents_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [p for p in items if isinstance(p, str) and Path(p).is_file()][:MAX_RECENTS]


def add_recent(path):
    path = str(Path(path).resolve())
    items = [p for p in load_recents() if p != path]
    items.insert(0, path)
    try:
        _recents_file().write_text(json.dumps(items[:MAX_RECENTS], ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    except OSError:
        pass


def project_info(path):
    """Résumé léger d'un projet pour la page de démarrage (sans tout charger)."""
    p = Path(path)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        mtime = p.stat().st_mtime
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    music = d.get("music")
    return {"path": str(p), "name": str(d.get("name") or p.stem), "modified": mtime,
            "clips": len(d.get("clips") or []), "music": Path(music).stem if music else None,
            "sons": len((d.get("sons") or {}).get("placements") or [])}


def remove_recent(path):
    path = str(Path(path).resolve())
    items = [p for p in load_recents() if p != path]
    try:
        _recents_file().write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


# ------------------------------------------------------ recherche clips ----

def default_clip_folders():
    """Dossiers où les logiciels d'enregistrement rangent souvent les clips Valorant."""
    home = Path.home()
    candidates = [home / "Videos", home / "Vidéos", home / "Videos" / "Valorant",
                  home / "Videos" / "Outplayed", home / "Videos" / "Medal",
                  home / "Videos" / "Radeon ReLive", home / "Videos" / "Captures"]
    seen, out = set(), []
    for c in candidates:
        if c.is_dir():
            r = c.resolve()
            if r not in seen:
                seen.add(r)
                out.append(c)
    return out


def scan_videos(folders, max_depth=4, limit=5000, is_cancelled=None):
    """Toutes les vidéos de ces dossiers (et sous-dossiers), les plus récentes d'abord."""
    found = {}
    for root in folders:
        root = Path(root)
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            if (is_cancelled and is_cancelled()) or len(found) >= limit:
                break
            if len(Path(dirpath).parts) - base_depth >= max_depth:
                dirnames[:] = []
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if Path(fn).suffix.lower() in VIDEO_EXT:
                    p = Path(dirpath) / fn
                    try:
                        found[str(p)] = p.stat().st_mtime
                    except OSError:
                        continue
    return [p for p, _ in sorted(found.items(), key=lambda kv: kv[1], reverse=True)]

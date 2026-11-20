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
    position: str = "les deux"                  # (ancien réglage, gardé pour compatibilité)
    videos: list[str] = field(default_factory=list)   # toutes les vidéos (gauche puis droite)
    gauche: list[str] = field(default_factory=list)   # vidéos de la main gauche
    droite: list[str] = field(default_factory=list)   # vidéos de la main droite

    def sync(self):
        self.videos = list(dict.fromkeys(self.gauche + self.droite))


@dataclass
class DashSettings:
    enabled: bool = True
    videos: list[str] = field(default_factory=list)   # toutes les vidéos (gauche puis droite)
    gauche: list[str] = field(default_factory=list)
    droite: list[str] = field(default_factory=list)

    def sync(self):
        self.videos = list(dict.fromkeys(self.gauche + self.droite))


def _hands(cls, data, **extra):
    """Charge kunai/dash ; un ancien projet (une seule liste) passe dans la main gauche."""
    data = data if isinstance(data, dict) else {}
    videos = [str(v) for v in data.get("videos") or []]
    g = [str(v) for v in data.get("gauche") or []]
    d = [str(v) for v in data.get("droite") or []]
    if not g and not d:
        if extra.get("position") == "droite":
            d = videos
        else:
            g = videos
    obj = cls(enabled=bool(data.get("enabled", True)), gauche=g, droite=d, **extra)
    obj.sync()
    return obj


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
    dash: DashSettings = field(default_factory=DashSettings)
    dashback: DashSettings = field(default_factory=DashSettings)
    dismiss: DashSettings = field(default_factory=DashSettings)
    render: dict = field(default_factory=dict)          # dernier rendu : fichier + coupes (pour les shakes)
    remaps: dict = field(default_factory=dict)
    shakes: dict = field(default_factory=dict)          # {"actif", "in", "out", "duree", "seed"}
    overlays: dict = field(default_factory=dict)        # {clip: réglages chroma} vidéo superposée (fond vert)
    markers: list = field(default_factory=list)         # [{"t", "type": clip|dash|kunai}] sur la musique          # {clip: {"couteau", "debut", "fin"}} time remap
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
            kunai=_hands(KunaiSettings, kunai, position=pos if pos in KUNAI_POSITIONS else "les deux"),
            sons={**default_sons(), **(data.get("sons") if isinstance(data.get("sons"), dict) else {})},
            dash=_hands(DashSettings, data.get("dash")),
            dashback=_hands(DashSettings, data.get("dashback")),
            dismiss=_hands(DashSettings, data.get("dismiss")),
            render=data.get("render") if isinstance(data.get("render"), dict) else {},
            remaps=data.get("remaps") if isinstance(data.get("remaps"), dict) else {},
            shakes=data.get("shakes") if isinstance(data.get("shakes"), dict) else {},
            overlays=data.get("overlays") if isinstance(data.get("overlays"), dict) else {},
            markers=[m for m in data.get("markers") or [] if isinstance(m, dict) and "t" in m],
            path=str(path),
        )
        if not isinstance(p.sons.get("placements"), list):
            p.sons["placements"] = []
        add_recent(path)
        return p

    # -- état
    def missing_files(self):
        """Fichiers du projet qui n'existent plus sur le PC (déplacés, supprimés...)."""
        files = [self.intro, self.outro, self.music, *self.clips, *self.kunai.videos, *self.dash.videos,
                 *self.dashback.videos, *self.dismiss.videos,
                 self.sons.get("paroles")]
        from . import vclip
        return [f for f in files if f and not vclip.exists(f)]

    def checklist(self):
        """Ce qui est prêt / ce qui manque, pour l'onglet Accueil."""
        return [
            ("Intro", bool(self.intro)),
            ("Musique", bool(self.music)),
            (f"Clips ({len(self.clips)})", bool(self.clips)),
            ("Kunai", (not self.kunai.enabled) or bool(self.kunai.videos)),
            ("Dash", (not self.dash.enabled) or bool(self.dash.videos)),
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


# ------------------------------------------- dossiers de clips (couteaux) ----

def clips_dir():
    """Ancien dossier des copies de clips (plus créé : l'app ne copie plus rien)."""
    return projects_dir().parent / "Clips"


def store_clip(src, knife):
    """Plus de copie : le clip reste à sa place sur le PC, l'app garde juste son chemin."""
    return str(src)


def _folders_file():
    return config_dir() / "dossiers_clips.json"


def load_clip_folders():
    """{nom du dossier (couteau): [chemins des clips]} — partagé entre tous les projets."""
    try:
        d = json.loads(_folders_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(d, dict):
        return {}
    return {str(k): [str(v) for v in vs if isinstance(v, str)] for k, vs in d.items() if isinstance(vs, list)}


# couteaux proposés dès l'installation : (nom, image dans app/assets/couteaux)
DEFAULT_KNIVES = [
    ("Primordium", "primordium.png"), ("Griffes Oni", "griffes_oni.png"),
    ("Kuronami Naru-Kami", "kuronami_naru_kami.png"), ("Kuronami no Yaiba", "kuronami_no_yaiba.png"),
    ("RGX 11z Pro", "rgx_11z_pro.png"), ("Xenohunter", "xenohunter.png"), ("EX.O Edge", "exo_edge.png"),
    ("Lame d'Aemondir", "aemondir.png"), ("Cyrax Fanblade", "cyrax_fanblade.png"),
    ("Lanceur de sorts d'Evori", "lanceur_evori.png"),
]


def _knife_asset(name):
    """Image fournie avec l'app (marche avec le .exe et avec les mises à jour légères)."""
    import sys
    roots = [Path(__file__).resolve().parents[1]]
    if hasattr(sys, "_MEIPASS"):
        roots.append(Path(sys._MEIPASS) / "app")
    for r in roots:
        f = r / "assets" / "couteaux" / name
        if f.is_file():
            return f
    return None


def ensure_default_knives():
    """Une seule fois : ajoute la liste des couteaux par défaut (avec leur image) à la bibliothèque.
    Un couteau qui existe déjà (même nom) garde ses clips ; un couteau supprimé ensuite ne revient pas."""
    marker = config_dir() / "couteaux_defaut_v1.ok"
    if marker.exists():
        return
    import shutil
    from . import timeremap
    folders = load_clip_folders()
    lower = {k.lower(): k for k in folders}
    cfg = timeremap.load()
    for name, img in DEFAULT_KNIVES:
        key = lower.get(name.lower(), name)
        folders.setdefault(key, [])
        src = _knife_asset(img)
        k = cfg["couteaux"].setdefault(key, {})
        if src is not None and not (k.get("carte") and Path(k["carte"]).is_file()):
            target = timeremap.knife_dir() / f"defaut_{img}"
            try:
                shutil.copyfile(src, target)
                k["carte"] = str(target)
            except OSError:
                pass
    save_clip_folders(folders)
    timeremap.save(cfg)
    try:
        marker.write_text("ok", encoding="utf-8")
    except OSError:
        pass


# catégories spéciales de « Mes clips » (en plus des couteaux) : nom -> symbole
SPECIAL_FOLDERS = {"Dash": "💨", "Kunai": "🗡", "Dash back": "↩", "Dismiss": "🌀"}
# partie du projet (main gauche / droite) qui va avec chaque catégorie
SPECIAL_ATTR = {"Dash": "dash", "Kunai": "kunai", "Dash back": "dashback", "Dismiss": "dismiss"}


def sync_special_folders(project=None):
    """Crée les catégories Dash / Kunai / Dash back / Dismiss dans « Mes clips » et y range
    les vidéos de ces parties du projet (sans doublon)."""
    folders = load_clip_folders()
    changed = False
    for name in SPECIAL_FOLDERS:
        if name not in folders:
            folders[name] = []
            changed = True
        if project is not None:
            st = getattr(project, SPECIAL_ATTR[name], None)
            for v in (st.videos if st else []):
                if v not in folders[name]:
                    folders[name].append(v)
                    changed = True
    if changed:
        save_clip_folders(folders)
    return folders


def save_clip_folders(folders):
    try:
        _folders_file().write_text(json.dumps(folders, ensure_ascii=False, indent=1), encoding="utf-8")
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


# ------------------------------------- migration : plus de copies de clips ----

def migrate_clips():
    """Une seule fois : remplace les anciennes copies de clips (Documents/AuraEdit/Clips/...) par leur
    équivalent sans fichier (morceau de la compilation d'origine) partout dans l'app (Mes clips,
    projets, réglages), puis supprime ces copies du PC. La liste est dans migration_clips.json."""
    f = projects_dir().parent / "migration_clips.json"
    if not f.is_file():
        return 0
    try:
        mp = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0

    def norm(s):
        return os.path.normcase(os.path.normpath(s))

    table = {norm(k): v for k, v in mp.items()}

    def fix_str(s):
        if len(s) < 500 and ("/" in s or "\\" in s):
            return table.get(norm(s), s)
        return s

    def fix(o):
        if isinstance(o, dict):
            return {fix_str(k) if isinstance(k, str) else k: fix(v) for k, v in o.items()}
        if isinstance(o, list):
            out = [fix(v) for v in o]
            if out and all(isinstance(v, str) for v in out):
                out = list(dict.fromkeys(out))           # sans doublon
            return out
        if isinstance(o, str):
            return fix_str(o)
        return o

    targets = list(config_dir().glob("*.json")) + list(projects_dir().glob("*.auraedit"))
    for t in targets:
        try:
            data = json.loads(t.read_text(encoding="utf-8"))
            new = fix(data)
            if new != data:
                t.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    removed = 0
    for old in mp:
        p = Path(old)
        try:
            if p.is_file():
                p.unlink()
                removed += 1
        except OSError:
            pass
    lib = projects_dir().parent / "Clips"
    if lib.is_dir():
        for d in sorted(lib.iterdir(), reverse=True):
            try:
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            except OSError:
                pass
        try:
            if not any(lib.iterdir()):
                lib.rmdir()
        except OSError:
            pass
    try:
        f.rename(f.with_suffix(".fait.json"))
    except OSError:
        pass
    return removed

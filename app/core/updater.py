"""Mises à jour automatiques via les Releases GitHub.

Ce fichier ne dépend pas de l'interface : il sait seulement
  1. demander à GitHub quelle est la dernière version publiée,
  2. télécharger le nouveau AuraEdit.exe (avec progression et vérification),
  3. remplacer l'exe en cours d'utilisation puis relancer le logiciel.

Astuce Windows utilisée : on ne peut pas SUPPRIMER un .exe en cours d'exécution,
mais on peut le RENOMMER. On renomme donc AuraEdit.exe -> AuraEdit.exe.old, on met
le nouveau à sa place, on relance, et l'ancien est supprimé au prochain démarrage.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from version import APP_NAME, ASSET_NAME, CODE_ASSET, GITHUB_REPO, __version__

# Permet de tester avec un faux serveur (variable d'environnement)
API_URL = os.environ.get("AURAEDIT_UPDATE_URL",
                         f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest")
TIMEOUT = 5  # secondes : sans internet, le logiciel démarre quand même vite


class UpdateError(Exception):
    """Erreur affichable à l'utilisateur."""


@dataclass
class UpdateInfo:
    version: str          # ex. "0.2.0"
    notes: str            # texte de la release (ce qui a changé)
    download_url: str     # lien direct vers AuraEdit.exe
    size: int             # taille attendue en octets
    sha256: str | None    # empreinte fournie par GitHub, si disponible
    page_url: str         # page web de la release
    kind: str = "exe"     # "code" = MAJ légère (seulement le code), "exe" = tout le logiciel


# ------------------------------------------------------------ versions ----

def parse_version(text):
    """'v1.2.10' -> (1, 2, 10). Ignore un éventuel suffixe ('-beta')."""
    nums = re.findall(r"\d+", (text or "").split("-")[0])
    if not nums:
        raise ValueError(f"Version illisible : {text!r}")
    parts = [int(n) for n in nums[:3]]
    return tuple(parts + [0] * (3 - len(parts)))


def is_newer(remote, local=__version__):
    try:
        return parse_version(remote) > parse_version(local)
    except ValueError:
        return False


# ------------------------------------------------------- vérification ----

def _request(url):
    return urllib.request.Request(url, headers={
        "User-Agent": f"{APP_NAME}/{__version__}",
        "Accept": "application/vnd.github+json",
    })


def clean_notes(text):
    """Garde seulement les nouveautés : retire les liens GitHub et le « Full Changelog »."""
    out = []
    for line in text.replace("\r", "").split("\n"):
        low = line.lower()
        if "full changelog" in low or "what's changed" in low or "new contributors" in low:
            continue
        if "github.com" in low or "http://" in low or "https://" in low:
            continue
        out.append(line)
    return "\n".join(out).strip()


def check_for_update(current=__version__):
    """Renvoie un UpdateInfo si une version plus récente existe, sinon None.

    Lève UpdateError seulement si GitHub répond quelque chose d'inattendu ;
    sans connexion, renvoie None (on ne dérange pas l'utilisateur)."""
    try:
        with urllib.request.urlopen(_request(API_URL), timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except OSError:          # pas d'internet, GitHub injoignable, 404...
        return None
    except json.JSONDecodeError as e:
        raise UpdateError("Réponse de GitHub illisible.") from e

    tag = data.get("tag_name") or ""
    if not is_newer(tag, current):
        return None
    assets = data.get("assets", [])
    asset = next((a for a in assets if a.get("name") == ASSET_NAME), None)
    code = next((a for a in assets if a.get("name") == CODE_ASSET), None)
    kind = "exe"
    if code is not None and is_frozen():
        asset, kind = code, "code"          # même base : pas besoin de retélécharger l'exe
    if asset is None:
        return None          # release publiée sans l'exe : on ignore
    digest = asset.get("digest") or ""
    return UpdateInfo(
        version=".".join(map(str, parse_version(tag))),
        notes=clean_notes(data.get("body") or ""),
        download_url=asset["browser_download_url"],
        size=int(asset.get("size") or 0),
        sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None,
        page_url=data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases",
        kind=kind,
    )


# -------------------------------------------------------- téléchargement ----

def download(info, dest, progress=None, is_cancelled=None, chunk=256 * 1024):
    """Télécharge la mise à jour dans `dest`, en vérifiant taille et empreinte.

    progress(reçu, total) est appelé régulièrement ; is_cancelled() permet d'annuler."""
    dest = Path(dest)
    tmp = dest.with_name(dest.name + ".part")
    sha = hashlib.sha256()
    received = 0
    try:
        with urllib.request.urlopen(_request(info.download_url), timeout=30) as resp, open(tmp, "wb") as f:
            total = int(resp.headers.get("Content-Length") or info.size or 0)
            while True:
                if is_cancelled and is_cancelled():
                    raise UpdateError("Téléchargement annulé.")
                block = resp.read(chunk)
                if not block:
                    break
                f.write(block)
                sha.update(block)
                received += len(block)
                if progress:
                    progress(received, total)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise UpdateError(f"Le téléchargement a échoué ({e}). Vérifie ta connexion.") from e
    except UpdateError:
        tmp.unlink(missing_ok=True)
        raise

    if info.size and received != info.size:
        tmp.unlink(missing_ok=True)
        raise UpdateError("Fichier téléchargé incomplet. Réessaie plus tard.")
    if info.sha256 and sha.hexdigest() != info.sha256:
        tmp.unlink(missing_ok=True)
        raise UpdateError("Le fichier téléchargé est corrompu (empreinte différente).")
    os.replace(tmp, dest)
    return dest


# ---------------------------------------------------------- installation ----

def is_frozen():
    """Vrai quand on tourne depuis AuraEdit.exe (et pas depuis le code Python)."""
    return bool(getattr(sys, "frozen", False))


def current_exe():
    return Path(sys.executable).resolve()


def download_path(exe=None):
    exe = Path(exe or current_exe())
    return exe.with_name(exe.name + ".download")


def install(new_file, exe=None):
    """Remplace l'exe par `new_file`. Remet l'ancien en place en cas d'échec."""
    exe = Path(exe or current_exe())
    old = exe.with_name(exe.name + ".old")
    try:
        old.unlink(missing_ok=True)
    except OSError:
        pass  # encore verrouillé : on écrasera avec os.replace
    try:
        os.replace(exe, old)
    except OSError as e:
        raise UpdateError("Impossible de remplacer le logiciel. Ferme les autres fenêtres "
                          "d'AuraEdit, ou déplace-le hors de « Program Files ».") from e
    try:
        os.replace(new_file, exe)
    except OSError as e:
        os.replace(old, exe)  # retour en arrière : le logiciel reste utilisable
        raise UpdateError("Installation impossible, l'ancienne version a été conservée.") from e
    return exe


def restart(exe=None):
    """Lance la nouvelle version (le programme appelant doit ensuite se fermer)."""
    exe = Path(exe or current_exe())
    env = dict(os.environ)
    # Pour un exe PyInstaller « onefile » : la nouvelle instance ne doit pas réutiliser
    # le dossier temporaire de l'ancienne.
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env.pop("_MEIPASS2", None)
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(exe)], env=env, close_fds=True, creationflags=flags, cwd=str(exe.parent))


def cleanup_leftovers(exe=None):
    """Au démarrage : supprime l'ancienne version et les téléchargements inachevés."""
    if exe is None and not is_frozen():
        return
    exe = Path(exe or current_exe())
    for suffix in (".old", ".download", ".download.part"):
        try:
            exe.with_name(exe.name + suffix).unlink(missing_ok=True)
        except OSError:
            pass


# ------------------------------------------------- MAJ légère (code seul) ----

def code_root():
    from app.core.project import config_dir
    d = config_dir() / "code"
    d.mkdir(parents=True, exist_ok=True)
    return d


def code_download_path():
    return code_root() / "maj.zip"


def install_code(zip_path, version):
    """Décompresse le nouveau code dans code/<version>/ et le choisit pour le prochain lancement."""
    import shutil
    import zipfile
    root = code_root()
    target = root / version
    tmp = root / (version + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                if name.startswith("/") or ".." in Path(name).parts:
                    raise UpdateError("Mise à jour invalide.")
            z.extractall(tmp)
        if not (tmp / "version.py").is_file() or not (tmp / "app").is_dir():
            raise UpdateError("Mise à jour incomplète.")
        shutil.rmtree(target, ignore_errors=True)
        os.replace(tmp, target)
        (root / "current.txt").write_text(version, encoding="utf-8")
    except (OSError, zipfile.BadZipFile) as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise UpdateError(f"Installation impossible : {e}") from e
    finally:
        Path(zip_path).unlink(missing_ok=True)
    for old in root.iterdir():                 # garde seulement la version installée
        if old.is_dir() and old.name != version:
            shutil.rmtree(old, ignore_errors=True)

"""Point d'entrée d'AuraEdit.  Lancer :  python main.py

Dans l'exe, les mises à jour « légères » ne remplacent pas l'exe : elles déposent seulement
le nouveau code dans %APPDATA%/AuraEdit/code/<version>/. Ce lanceur l'utilise s'il est plus
récent que le code fourni dans l'exe et compatible (même BASE), sinon il garde le code de l'exe.
"""
import os
import re
import shutil
import sys
from pathlib import Path


def _code_root():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "AuraEdit" / "code"


def _ver(text):
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3])


def _purge():
    for m in list(sys.modules):
        if m == "version" or m == "app" or m.startswith("app."):
            del sys.modules[m]


def _downloaded_code():
    """Dossier du code téléchargé à utiliser, ou None."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        import version as bundled
        root = _code_root()
        folder = root / (root / "current.txt").read_text(encoding="utf-8").strip()
        txt = (folder / "version.py").read_text(encoding="utf-8")
        base = int(re.search(r"BASE = (\d+)", txt).group(1))
        ver = re.search(r'__version__ = "([^"]+)"', txt).group(1)
        if base != getattr(bundled, "BASE", None) or _ver(ver) <= _ver(bundled.__version__):
            return None
        return folder
    except Exception:
        return None


def run():
    folder = _downloaded_code()
    if folder is not None:
        _purge()
        sys.path.insert(0, str(folder))
        try:
            from app.launcher import main
        except Exception:                     # code téléchargé abîmé : retour au code de l'exe
            sys.path.remove(str(folder))
            _purge()
            try:
                (_code_root() / "current.txt").unlink()
                shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                pass
            from app.launcher import main
    else:
        from app.launcher import main
    return main()


if __name__ == "__main__":
    sys.exit(run())

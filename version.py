"""Identité de l'application. Change __version__ avant chaque nouvelle release."""

__version__ = "0.4.2"
APP_NAME = "AuraEdit"
GITHUB_REPO = "auragpro/AuraEdit"     # dépôt GitHub où sont publiées les mises à jour
ASSET_NAME = "AuraEdit.exe"           # nom du fichier attaché à chaque Release
# BASE : à augmenter seulement quand l'exe doit être retéléchargé (nouvelle bibliothèque dans
# requirements.txt, nouveau module Python/Qt jamais utilisé avant). Sinon la MAJ ne télécharge
# que le code (quelques centaines de Ko).
BASE = 1
CODE_ASSET = f"AuraEdit-code-base{BASE}.zip"

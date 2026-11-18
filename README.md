# AuraEdit

Logiciel qui fabrique tes edits Valorant : intro + musique + clips + kunais de Jett → MP4.

**Version 0.1.0** : mises à jour automatiques, page de démarrage, mode édition avec les 5 onglets
(choix des fichiers, ordre des clips, réglages des kunais, sauvegarde automatique).
La génération de la vidéo arrive à la prochaine étape.

## Lancer le logiciel (depuis le code)

1. Installe Python 3.10+ (coche *Add Python to PATH*).
2. Double-clique sur **`lancer.bat`** (il installe PyQt6 la première fois puis ouvre l'app).

## Fabriquer AuraEdit.exe

Double-clique sur **`build\build.bat`** → le fichier sort dans `dist\AuraEdit.exe`.

## Publier une mise à jour (comme pour AuraScript)

1. Crée le dépôt GitHub **`auragpro/AuraEdit`** et envoie-y ce dossier (une seule fois).
2. Pour chaque nouvelle version :
   1. change le numéro dans **`version.py`** (ex. `__version__ = "0.2.0"`) ;
   2. commit + push ;
   3. crée et pousse le tag correspondant :
      ```
      git tag v0.2.0
      git push origin v0.2.0
      ```
3. GitHub fabrique `AuraEdit.exe` tout seul (onglet *Actions*) et le publie dans une *Release*.
   Au prochain lancement, chaque AuraEdit installé affiche la popup de mise à jour.

Le tag doit correspondre à `version.py`, sinon la publication s'arrête avec un message clair.
Tu peux modifier le texte de la Release sur GitHub : c'est lui qui s'affiche dans la popup.

## Organisation du code

```
main.py                   point d'entrée (thème, gestion des erreurs, lancement)
version.py                numéro de version + dépôt GitHub
app/core/updater.py       mises à jour : vérifier, télécharger, remplacer l'exe, relancer
app/core/project.py       projets (.auraedit), derniers projets, recherche des clips sur le PC
app/core/detection/       détection des kills (sera branchée plus tard)
app/ui/main_window.py     vérification MAJ -> page de démarrage -> mode édition
app/ui/start_page.py      page de démarrage (« Commencer un edit » + derniers edits)
app/ui/update_dialog.py   popup « Nouvelle mise à jour »
app/ui/edit_view.py       barre latérale + onglets
app/ui/tabs/*.py          un fichier par onglet
app/ui/workers.py         tâches en arrière-plan (la fenêtre ne se fige jamais)
app/ui/widgets.py         composants réutilisés (choix de fichier, titres)
app/ui/style.py           couleurs et thème
tests/                    tests automatiques des mises à jour
```

## Où sont mes fichiers ?

- Projets : `Documents\AuraEdit\Projets\*.auraedit` (sauvegarde automatique à chaque changement)
- Derniers projets et journal d'erreurs : `%APPDATA%\AuraEdit\`
  (en cas de bug, envoie-moi `erreurs.log`)

# AuraEdit

Logiciel qui fabrique tes edits Valorant : intro + musique + clips + kunais de Jett → MP4.

**Version 0.2.0** : mises à jour automatiques, page de démarrage, 6 onglets (Accueil, Intro, Musique,
Clips, Sons IA, Kunais Jett) avec sauvegarde automatique. La génération de la vidéo arrive ensuite.

## Onglet Sons IA

1. Range tes sons dans un dossier, idéalement en sous-dossiers : `Vandal`, `Sheriff`, `Woosh`,
   `Impact`, `Riser`... (l'IA reconnaît la catégorie dans le nom du dossier ou du fichier).
2. Choisis la musique (onglet Musique), le dossier de sons, et si tu veux un fichier de paroles
   `.lrc` + des mots-clés (ex. `bang, tire`) : un son sera calé sur ces mots.
3. « Analyser et générer » : tempo, beats, temps forts, drops et attaques de voix sont détectés,
   puis l'IA place les sons. Mauvais tempo ? Boutons ÷2 / ×2.
4. Corrige : supprimer, changer de son, double-clic sur la timeline pour ajouter. Puis
   **« Valider : l'IA apprend »**. Chaque choix entraîne l'IA (fichier `%APPDATA%\AuraEdit\sons_ia_modele.json`).
5. « Écouter l'aperçu » ou « Exporter les WAV » (musique + sons, et sons seuls pour ton logiciel de montage).

### Apprendre d'un edit déjà fait

« Apprendre d'un edit déjà fait... » : donne un edit fini (mp4 ou audio) **et sa musique d'origine**.
L'IA cale la musique dans l'edit (intro avant, morceau commencé plus loin, volume changé : OK),
retire la musique, puis reconnaît chacun des sons de ton dossier dans ce qui reste. Elle replace
chaque son dans la musique (drop, temps fort, caisse claire, voix...) et apprend aussi les moments
où tu n'as rien mis. Tu peux décocher les détections fausses avant de cliquer « Apprendre ».

Limites : les sons doivent être les mêmes fichiers que ceux de ton dossier ; la musique doit être
utilisée en un seul morceau continu (pas recoupée ni accélérée) ; un son posé exactement sur une
grosse caisse très forte peut être raté.

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

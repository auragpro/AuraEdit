@echo off
REM Fabrique dist\AuraEdit.exe (un seul fichier, sans console)
cd /d "%~dp0\.."
python -m pip install -r requirements-dev.txt || goto :erreur
python -m unittest discover tests || goto :erreur
python -m PyInstaller --noconfirm --clean --onefile --windowed --name AuraEdit --icon app\assets\logo.png --add-data "app\assets;app\assets" --collect-all imageio_ffmpeg main.py || goto :erreur
echo.
echo OK : dist\AuraEdit.exe
pause
exit /b 0
:erreur
echo ECHEC de la fabrication, lis le message au-dessus.
pause
exit /b 1

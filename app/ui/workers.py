"""Tâches lancées en arrière-plan pour que la fenêtre ne se fige jamais.

Règle de Qt : on ne touche JAMAIS à l'interface depuis un thread. Les threads
envoient des signaux ; Qt les livre à la fenêtre dans le thread principal.
"""
from PyQt6.QtCore import QThread, pyqtSignal

from app.core import project, updater


class UpdateCheckThread(QThread):
    """Demande à GitHub s'il existe une nouvelle version."""
    found = pyqtSignal(object)      # UpdateInfo
    nothing = pyqtSignal()          # à jour, ou pas d'internet

    def run(self):
        try:
            info = updater.check_for_update()
        except Exception:           # une MAJ ratée ne doit jamais empêcher de lancer l'app
            info = None
        if info:
            self.found.emit(info)
        else:
            self.nothing.emit()


class DownloadThread(QThread):
    """Télécharge la mise à jour."""
    progress = pyqtSignal(object, object)   # reçu, total (octets)
    done = pyqtSignal(str)                  # chemin du fichier téléchargé
    failed = pyqtSignal(str)                # message d'erreur

    def __init__(self, info, dest, parent=None):
        super().__init__(parent)
        self.info = info
        self.dest = dest
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            path = updater.download(self.info, self.dest,
                                    progress=lambda r, t: self.progress.emit(r, t),
                                    is_cancelled=lambda: self._cancel)
            self.done.emit(str(path))
        except updater.UpdateError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"Erreur inattendue : {e}")


class ScanThread(QThread):
    """Cherche les vidéos dans des dossiers du PC."""
    done = pyqtSignal(list)

    def __init__(self, folders, parent=None):
        super().__init__(parent)
        self.folders = folders
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            result = project.scan_videos(self.folders, is_cancelled=lambda: self._cancel)
        except Exception:
            result = []
        self.done.emit(result)


class AnalyzeThread(QThread):
    """Analyse la musique (tempo, beats, drops, voix, paroles)."""
    done = pyqtSignal(object)       # music_analysis.Analysis
    failed = pyqtSignal(str)

    def __init__(self, music, lrc_path=None, keywords=(), forced_tempo=None, parent=None):
        super().__init__(parent)
        self.music, self.lrc_path, self.keywords, self.forced_tempo = music, lrc_path, keywords, forced_tempo

    def run(self):
        from app.core import audio, music_analysis
        try:
            y = audio.load(self.music, music_analysis.SR, 1)
            lrc = None
            if self.lrc_path:
                try:
                    with open(self.lrc_path, encoding="utf-8-sig", errors="replace") as f:
                        lrc = f.read()
                except OSError:
                    lrc = None
            self.done.emit(music_analysis.analyze(y, lrc, self.keywords, self.forced_tempo))
        except Exception as e:
            self.failed.emit(str(e))


class RenderThread(QThread):
    """Mixe la musique et les sons dans des fichiers WAV."""
    done = pyqtSignal(str, str)     # chemin mix, chemin sons seuls
    failed = pyqtSignal(str)

    def __init__(self, music, placements, out_mix, out_sfx, parent=None):
        super().__init__(parent)
        self.music, self.placements, self.out_mix, self.out_sfx = music, placements, out_mix, out_sfx

    def run(self):
        from app.core import sound_ai
        try:
            sound_ai.render(self.music, self.placements, self.out_mix, self.out_sfx)
            self.done.emit(str(self.out_mix), str(self.out_sfx or ""))
        except Exception as e:
            self.failed.emit(str(e))


class ListenThread(QThread):
    """L'IA écoute un edit déjà fait et retrouve les sound kills."""
    progress = pyqtSignal(str, float)
    done = pyqtSignal(object)       # edit_learning.EditExample
    failed = pyqtSignal(str)

    def __init__(self, edit, music, library, parent=None):
        super().__init__(parent)
        self.edit, self.music, self.library = edit, music, list(library)

    def run(self):
        from app.core import edit_learning
        try:
            ex = edit_learning.listen(self.edit, self.music, self.library,
                                      progress=lambda txt, f: self.progress.emit(txt, float(f)))
            self.done.emit(ex)
        except Exception as e:
            self.failed.emit(str(e))



class CutsThread(QThread):
    """Trouve les transitions d'un edit vidéo et analyse son audio."""
    done = pyqtSignal(object, object)   # cuts, analysis
    failed = pyqtSignal(str)

    def __init__(self, video, parent=None):
        super().__init__(parent)
        self.video = video

    def run(self):
        from app.core import audio, music_analysis, video_cuts
        try:
            cuts = video_cuts.detect_cuts(self.video)
            y = audio.load(self.video, music_analysis.SR, 1)
            self.done.emit(cuts, music_analysis.analyze(y))
        except Exception as e:
            self.failed.emit(str(e))


class RenderThread(QThread):
    """Rendu de l'edit en MP4."""
    progress = pyqtSignal(float, str)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, project, output, parent=None):
        super().__init__(parent)
        self.project = project
        self.output = output
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        from app.core import render
        try:
            res = render.render(self.project, self.output, progress=self.progress.emit,
                                is_cancelled=lambda: self._cancel)
        except render.Cancelled:
            self.failed.emit("Rendu annulé.")
            return
        except Exception as e:
            self.failed.emit(str(e) or e.__class__.__name__)
            return
        self.done.emit(res)


class FuncThread(QThread):
    """Lance une fonction longue en arrière-plan. fn(progress) -> résultat."""
    progress = pyqtSignal(str, float)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            res = self.fn(lambda txt, frac: self.progress.emit(str(txt), float(frac)))
        except Exception as e:
            self.failed.emit(str(e) or e.__class__.__name__)
            return
        self.done.emit(res)

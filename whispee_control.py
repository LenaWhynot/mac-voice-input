import os, sys, subprocess, time, threading
from pathlib import Path
import rumps

UID = str(os.getuid())
LABEL = "com.whisper.dictation"
PLIST = os.path.expanduser("~/Library/LaunchAgents/com.whisper.dictation.plist")
TRIGGER = os.path.expanduser("~/.config/whisper-skill/toggle.trigger")
FINALIZE = os.path.expanduser("~/.config/whisper-skill/finalize.trigger")
LAST = os.path.expanduser("~/.config/whisper-skill/last_dictation.txt")
HISTORY = os.path.expanduser("~/.config/whisper-skill/dictation-history.txt")
_HERE = os.path.dirname(os.path.abspath(__file__))          # <DIR>/control
_ICON = os.path.join(_HERE, "menubar_icon.png")
VIEWER = os.path.join(_HERE, "history_viewer.py")
# venv-питон рядом со скиллом (в нём есть tkinter); фолбэк — текущий интерпретатор
_VENV_PY = os.path.join(os.path.dirname(_HERE), ".venv", "bin", "python")
VIEWER_PY = _VENV_PY if os.path.exists(_VENV_PY) else sys.executable


def _running():
    return subprocess.run(["pgrep", "-f", "Whispee.app/Contents/MacOS/Whispee"],
                          capture_output=True).returncode == 0

def _start():
    subprocess.run(["launchctl", "bootstrap", f"gui/{UID}", PLIST], capture_output=True)

def _stop():
    subprocess.run(["launchctl", "bootout", f"gui/{UID}/{LABEL}"], capture_output=True)


class WhispeeControl(rumps.App):
    def __init__(self):
        super().__init__("", icon=_ICON, template=False, quit_button=None)
        # Заголовок-название (некликабельный) + разделы
        header = rumps.MenuItem("Whispee")          # без callback → серый заголовок
        self.menu = [
            header,
            None,
            "Начать / остановить запись",            # активировать микрофон из меню (доп. к Option)
            None,
            "Скопировать последнюю диктовку",         # если вставка промахнулась мимо поля → в буфер
            "Открыть историю диктовок",
            None,
            "Перезапустить",
            "Полностью выключить",
            None,
            "Открыть лог",
        ]

    @rumps.clicked("Начать / остановить запись")
    def record(self, _):
        # «Трогаем» файл-триггер — движок замечает и переключает запись.
        if not _running():
            _start(); time.sleep(2)
        Path(TRIGGER).parent.mkdir(parents=True, exist_ok=True)
        Path(TRIGGER).touch()

    @rumps.clicked("Скопировать последнюю диктовку")
    def copylast(self, _):
        # Спасалка «ничего не пропадает зря»: если запись ЗАСТРЯЛА (стоп по хоткею
        # не сработал — мёртвый event-tap), сначала ПРИНУДИТЕЛЬНО завершаем её через
        # finalize-триггер (путь независим от хоткея), ждём свежий текст, потом
        # кладём в буфер. Если ничего не записывалось — просто копируем прошлую.
        # Работу — в фон-поток, иначе rumps-меню зависнет на время ожидания.
        threading.Thread(target=self._copylast_worker, daemon=True).start()

    def _copylast_worker(self):
        before = os.path.getmtime(LAST) if os.path.exists(LAST) else 0.0
        # Просим движок завершить текущую (возможно застрявшую) запись сейчас.
        try:
            Path(FINALIZE).parent.mkdir(parents=True, exist_ok=True)
            Path(FINALIZE).touch()
        except Exception:
            pass
        # Ждём до ~15с, пока движок допишет свежую диктовку (стоп+транскрипция
        # застрявшей записи). Если ничего не писалось — mtime не сдвинется.
        got_fresh = False
        deadline = time.time() + 15
        while time.time() < deadline:
            time.sleep(0.4)
            now_m = os.path.getmtime(LAST) if os.path.exists(LAST) else 0.0
            if now_m > before:
                got_fresh = True
                break
        try:
            with open(LAST, encoding="utf-8") as f:
                txt = f.read()
        except FileNotFoundError:
            rumps.notification("Whispee", "", "Пока нет ни одной диктовки")
            return
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(txt.encode("utf-8"))
        if got_fresh:
            rumps.notification("Whispee", "", "Текущая запись сохранена и в буфере — жми Cmd+V")
        else:
            rumps.notification("Whispee", "", "Последняя диктовка в буфере — жми Cmd+V")

    @rumps.clicked("Открыть историю диктовок")
    def openhistory(self, _):
        # Нативное окно (Tkinter) с поиском и копированием по записи —
        # не блокнот. Запускаем venv-питоном (в нём есть tkinter).
        if os.path.exists(VIEWER):
            subprocess.Popen([VIEWER_PY, VIEWER])
        elif os.path.exists(HISTORY):
            subprocess.run(["open", HISTORY])      # фолбэк: текстовый файл
        else:
            rumps.notification("Whispee", "", "История пока пуста")

    @rumps.clicked("Перезапустить")
    def restart(self, _):
        _stop(); time.sleep(2); _start()

    @rumps.clicked("Полностью выключить")
    def power(self, sender):
        if _running():
            _stop()
            sender.title = "Включить"
        else:
            _start()
            sender.title = "Полностью выключить"

    @rumps.clicked("Открыть лог")
    def openlog(self, _):
        subprocess.run(["open", "/tmp/whisper_dictation.log"])


_wake_observer = None  # держим ссылку, иначе PyObjC соберёт observer мусором


def _install_wake_restart():
    """Перезапускать диктовку при пробуждении мака.

    Корень утреннего «виспи топит»: после сна macOS гасит глобальный
    event-tap, и правый Option перестаёт доходить до Whispee.app —
    keepalive-патч в движке не спасает, т.к. после ДОЛГОГО сна disable-маркер
    не приходит (tap молча мёртв). Лечит только рестарт процесса.

    Контроллер — живое NSApplication, поэтому ловим NSWorkspaceDidWakeNotification
    и делаем bootout+bootstrap (тот же путь, что «Перезапустить» в меню).
    Рестарт уносим в фон-поток: не блокируем менюбар на sleep(2), а движок и так
    грузит модель лениво на первой диктовке (warmup=false).
    """
    global _wake_observer
    try:
        from AppKit import NSWorkspace, NSObject
    except Exception:
        return

    def _restart_async():
        _stop(); time.sleep(2); _start()

    class _WakeObserver(NSObject):
        def handleWake_(self, _note):
            import threading
            threading.Thread(target=_restart_async, daemon=True).start()

    try:
        _wake_observer = _WakeObserver.alloc().init()
        nc = NSWorkspace.sharedWorkspace().notificationCenter()
        nc.addObserver_selector_name_object_(
            _wake_observer, b"handleWake:",
            "NSWorkspaceDidWakeNotification", None,
        )
    except Exception:
        _wake_observer = None


def _hide_from_dock():
    """Контроль — менюбар-приложение, ему не место в доке. rumps НЕ ставит
    accessory-режим, а под launchd (голый python, без бандла) иконка Python
    появляется в доке — и KeepAlive воскрешает её при закрытии («не закрывается»).
    Ставим NSApplicationActivationPolicyAccessory → живём только в менюбаре.
    """
    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().setActivationPolicy_(1)  # 1 = Accessory
    except Exception:
        pass


if __name__ == "__main__":
    _hide_from_dock()
    _install_wake_restart()
    WhispeeControl().run()

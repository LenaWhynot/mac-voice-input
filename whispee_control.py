import os, subprocess, time
from pathlib import Path
import rumps

UID = str(os.getuid())
LABEL = "com.whisper.dictation"
PLIST = os.path.expanduser("~/Library/LaunchAgents/com.whisper.dictation.plist")
TRIGGER = os.path.expanduser("~/.config/whisper-skill/toggle.trigger")
_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menubar_icon.png")


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


if __name__ == "__main__":
    WhispeeControl().run()

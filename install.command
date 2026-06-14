#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
#  Whispee — голосовой ввод на Mac. Локальный Whisper, бесплатно, без облака.
#  Для Apple Silicon (M1/M2/M3/M4).
#
#  Этот установщик САМ скачивает оригинальный движок Whisper-Skill
#  (github.com/Mobiss11/Whisper-Skill, автор Mobiss11) и накатывает поверх
#  улучшения (improvements.patch). Чужой код берётся напрямую у автора —
#  репозиторий его не хранит.
#
#  Что ставит: движок + модель large-v3-turbo (Metal), приложение «Whispee»
#  с иконкой, авто-вставку, автозапуск и иконку управления в меню-баре.
#
#  Запуск: двойной клик. Если macOS не открывает — правый клик → «Открыть».
# ──────────────────────────────────────────────────────────────────────
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DIR="$HOME/whisper-dictation"
CFG_DIR="$HOME/.config/whisper-skill"
MODEL_DIR="$DIR/models/whisper-large-v3-turbo"
APP="$HOME/Applications/Whispee.app"
PLIST="$HOME/Library/LaunchAgents/com.whisper.dictation.plist"
CTRL_PLIST="$HOME/Library/LaunchAgents/com.whispee.control.plist"
UID_NUM="$(id -u)"

say(){ printf "\n\033[1m%s\033[0m\n" "$1"; }
ok(){ printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn(){ printf "  \033[33m⚠\033[0m %s\n" "$1"; }

say "🎤 Установка Whispee — голосовой ввод на Mac"

[ "$(uname -m)" = "arm64" ] || { warn "Нужен Mac на Apple Silicon (M1/M2/M3/M4)."; read -r -p "Enter…" _; exit 1; }
ok "Apple Silicon"
command -v brew >/dev/null 2>&1 || { warn "Нет Homebrew. Поставь с https://brew.sh и запусти снова."; read -r -p "Enter…" _; exit 1; }
ok "Homebrew"

say "Ставлю Python 3.13, Tk и ffmpeg…"
brew list python@3.13 >/dev/null 2>&1 || brew install python@3.13
# python-tk@3.13 — для нативного окна «История диктовок» (Tkinter)
brew list python-tk@3.13 >/dev/null 2>&1 || brew install python-tk@3.13 || warn "python-tk не поставился — окно истории недоступно, останется текстовый файл."
command -v ffmpeg >/dev/null 2>&1 || brew install ffmpeg
PY="$(brew --prefix python@3.13)/bin/python3.13"
FFDIR="$(dirname "$(command -v ffmpeg)")"
ok "Python 3.13 + Tk + ffmpeg ($FFDIR)"

say "Скачиваю движок (оригинал) и накатываю улучшения…"
[ -d "$DIR/examples" ] || git clone --depth 1 https://github.com/Mobiss11/Whisper-Skill "$DIR"
cd "$DIR"
git apply "$HERE/improvements.patch" 2>/dev/null \
  || patch -p1 --forward --silent < "$HERE/improvements.patch" 2>/dev/null \
  || warn "Улучшения уже наложены или оригинал изменился — продолжаю."
ok "Движок готов"

say "Окружение и зависимости (пара минут)…"
[ -d "$DIR/.venv" ] || "$PY" -m venv "$DIR/.venv"
"$DIR/.venv/bin/python" -m pip install -q --upgrade pip
"$DIR/.venv/bin/pip" install -q mlx-whisper sounddevice soundfile pynput pyperclip numpy py2app rumps
ok "Зависимости установлены"

say "Скачиваю модель large-v3-turbo (~1.6 ГБ) с ModelScope (без HuggingFace-лимитов)…"
mkdir -p "$MODEL_DIR"
MS="https://modelscope.cn/models/mlx-community/whisper-large-v3-turbo/resolve/master"
curl -fL --retry 3 "$MS/config.json" -o "$MODEL_DIR/config.json"
if [ ! -s "$MODEL_DIR/weights.safetensors" ]; then
  curl -fL --retry 3 "$MS/weights.safetensors" -o "$MODEL_DIR/weights.safetensors"
fi
if [ -s "$MODEL_DIR/weights.safetensors" ]; then ok "Модель скачана ($MODEL_DIR)"; else warn "Модель не докачалась — при первом вводе попробует HuggingFace."; fi

say "Пишу конфиг и звуки…"
mkdir -p "$CFG_DIR"
# Усиленный Purr — стандартный звук старта записи (оригинал слишком тих)
ffmpeg -y -i /System/Library/Sounds/Purr.aiff \
  -af "volume=8dB,alimiter=limit=0.95" \
  "$CFG_DIR/purr_loud.aiff" -loglevel quiet && ok "Звук старта записи готов" || warn "Не удалось создать звук — будет тихий оригинал"
cat > "$CFG_DIR/voice_dictation.json" <<JSON
{
  "hotkey": "<alt_r>",
  "mode": "toggle",
  "language": "ru",
  "model": "$MODEL_DIR",
  "backend": "mlx",
  "paste_mode": "uni",
  "sample_rate": 16000,
  "channels": 1,
  "auto_paste": true,
  "play_sound": true,
  "show_tray": false,
  "show_cursor_indicator": false,
  "log_file": "/tmp/whisper_dictation.log",
  "trim_silence_ms": 200,
  "min_duration_ms": 300,
  "mac_low_cpu_mode": true,
  "warmup": false
}
JSON
ok "Конфиг: правый Option (toggle), язык ru, turbo, авто-вставка (юникод, не зависит от раскладки, буфер не трогает)"

say "Собираю приложение «Whispee» с иконкой…"
# иконка .icns из 1024 PNG
ICONSET="$DIR/.iconset"; rm -rf "$ICONSET"; mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$HERE/app_icon_1024.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1
  d=$((s*2)); sips -z $d $d "$HERE/app_icon_1024.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null 2>&1
done
iconutil -c icns "$ICONSET" -o "$DIR/Whispee.icns" 2>/dev/null || true
# entry + setup для py2app (alias)
mkdir -p "$DIR/appbuild"
cat > "$DIR/appbuild/Whispee.py" <<PY
import sys, os
SKILL = os.path.expanduser("~/whisper-dictation")
os.chdir(SKILL); sys.path.insert(0, SKILL)
from examples import voice_dictation
voice_dictation.main()
PY
cat > "$DIR/appbuild/setup.py" <<PY
from setuptools import setup
setup(app=["Whispee.py"], setup_requires=["py2app"], options={"py2app": {
  "argv_emulation": False, "iconfile": "$DIR/Whispee.icns",
  "plist": {"CFBundleDisplayName":"Whispee","CFBundleName":"Whispee",
            "CFBundleIdentifier":"com.lenawhynot.whispee","CFBundleShortVersionString":"1.0",
            "LSUIElement":True,"NSMicrophoneUsageDescription":"Whispee распознаёт вашу речь локально."}}})
PY
APP_OK=0
if ( cd "$DIR/appbuild" && "$DIR/.venv/bin/python" setup.py py2app -A >/tmp/whispee_build.log 2>&1 ); then
  mkdir -p "$HOME/Applications"; rm -rf "$APP"
  cp -R "$DIR/appbuild/dist/Whispee.app" "$HOME/Applications/" && APP_OK=1
fi
if [ "$APP_OK" = "1" ]; then APPEXE="$APP/Contents/MacOS/Whispee"; ok "Приложение Whispee.app собрано"; else APPEXE="$DIR/.venv/bin/python"; warn "Сборка приложения не удалась — ставлю обычный режим (в разрешениях будет Python)."; fi

say "Автозапуск (launchd) + ffmpeg в PATH…"
mkdir -p "$HOME/Library/LaunchAgents"
if [ "$APP_OK" = "1" ]; then PROG="<string>$APPEXE</string>"; else PROG="<string>$APPEXE</string><string>-m</string><string>examples.voice_dictation</string>"; fi
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.whisper.dictation</string>
  <key>ProgramArguments</key><array>$PROG</array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Interactive</string>
  <key>EnvironmentVariables</key><dict>
    <key>PYTHONUNBUFFERED</key><string>1</string>
    <key>PATH</key><string>$FFDIR:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key><string>/tmp/whisper_dictation.log</string>
  <key>StandardErrorPath</key><string>/tmp/whisper_dictation.err</string>
</dict></plist>
PLISTEOF
launchctl bootout "gui/$UID_NUM/com.whisper.dictation" 2>/dev/null || true
sleep 1; launchctl bootstrap "gui/$UID_NUM" "$PLIST" 2>/dev/null || true
ok "Автозапуск настроен"

say "Иконка управления в меню-баре…"
mkdir -p "$DIR/control"
cp "$HERE/whispee_control.py" "$DIR/control/whispee_control.py"
cp "$HERE/menubar_icon.png" "$DIR/control/menubar_icon.png"
cp "$HERE/history_viewer.py" "$DIR/control/history_viewer.py"   # нативное окно истории
cat > "$CTRL_PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.whispee.control</string>
  <key>ProgramArguments</key><array><string>$DIR/.venv/bin/python</string><string>$DIR/control/whispee_control.py</string></array>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardErrorPath</key><string>/tmp/whispee_control.err</string>
</dict></plist>
PLISTEOF
launchctl bootout "gui/$UID_NUM/com.whispee.control" 2>/dev/null || true
sleep 1; launchctl bootstrap "gui/$UID_NUM" "$CTRL_PLIST" 2>/dev/null || true
ok "Меню-бар 🎤 настроен"

say "Приложение «История диктовок» на рабочий стол…"
HIST_APP="$HOME/Desktop/История диктовок.app"
rm -rf "$HIST_APP"
# applet запускает окно venv-питоном, detached (& → applet сразу выходит)
if osacompile -o "$HIST_APP" -e "do shell script \"'$DIR/.venv/bin/python' '$DIR/control/history_viewer.py' > /dev/null 2>&1 &\"" 2>/dev/null; then
  [ -f "$DIR/Whispee.icns" ] && cp "$DIR/Whispee.icns" "$HIST_APP/Contents/Resources/applet.icns"
  /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile applet" "$HIST_APP/Contents/Info.plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string applet" "$HIST_APP/Contents/Info.plist" 2>/dev/null || true
  touch "$HIST_APP"
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$HIST_APP" 2>/dev/null || true
  ok "«История диктовок.app» на рабочем столе (двойной клик — окно с поиском и копированием)"
else
  warn "Не собрал приложение истории — открыть можно из меню-бара 🎤 → «Открыть историю диктовок»."
fi

# Разрешения
PYAPP="$("$DIR/.venv/bin/python" - <<'PYEOF'
import ctypes
b=ctypes.create_string_buffer(4096); s=ctypes.c_uint32(4096)
ctypes.CDLL(None)._NSGetExecutablePath(b, ctypes.byref(s)); print(b.value.decode())
PYEOF
)"
if [ "$APP_OK" = "1" ]; then GRANT="$APP"; else GRANT="$PYAPP"; fi
printf "%s" "$GRANT" | pbcopy
say "ПОЧТИ ГОТОВО — 2 галочки (Apple требует руками). Путь СКОПИРОВАН в буфер:"
echo "  $GRANT"
echo "  В каждой панели: + → Cmd+Shift+G → Cmd+V → Enter → Open → включи тумблер."
echo "    1) Универсальный доступ (Accessibility)"
echo "    2) Мониторинг ввода (Input Monitoring)"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true
sleep 2
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent" 2>/dev/null || true
say "После галочек заработает само. Пользоваться: тык ПРАВОГО Option → говоришь → ещё тык → текст вставится."
echo "  Управление — иконка 🎤 в меню-баре (запуск записи, перезапуск, выключить)."
ok "Готово."
read -r -p "Enter для выхода…" _

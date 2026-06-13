#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
#  Голосовая диктовка на Mac — локальный Whisper. Бесплатно, без облака.
#  Для Apple Silicon (M1/M2/M3/M4).
#
#  Этот установщик САМ скачивает оригинальный движок Whisper-Skill
#  (github.com/Mobiss11/Whisper-Skill, автор Mobiss11) и накатывает поверх
#  набор улучшений (improvements.patch): надёжная вставка текста печатью,
#  toggle по правому Option, звуки, авто-стоп, фикс прогрева. Чужой код
#  скачивается напрямую у автора — этот репозиторий его не хранит.
#
#  Запуск: двойной клик. Если macOS не даёт открыть —
#  правый клик по файлу → «Открыть» → «Открыть».
# ──────────────────────────────────────────────────────────────────────
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DIR="$HOME/whisper-dictation"
CFG_DIR="$HOME/.config/whisper-skill"
PLIST="$HOME/Library/LaunchAgents/com.whisper.dictation.plist"
UID_NUM="$(id -u)"

say(){ printf "\n\033[1m%s\033[0m\n" "$1"; }
ok(){ printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn(){ printf "  \033[33m⚠\033[0m %s\n" "$1"; }

say "🎤 Установка локальной голосовой диктовки (Whisper)"

# 0. Только Apple Silicon
[ "$(uname -m)" = "arm64" ] || { warn "Нужен Mac на Apple Silicon (M1/M2/M3/M4)."; read -r -p "Enter…" _; exit 1; }
ok "Apple Silicon"

# 1. Homebrew
command -v brew >/dev/null 2>&1 || { warn "Нет Homebrew. Поставь с https://brew.sh и запусти снова."; read -r -p "Enter…" _; exit 1; }
ok "Homebrew"

# 2. Python 3.13 + ffmpeg (свежий системный Python без wheels для mlx — нужен 3.13)
say "Ставлю Python 3.13 и ffmpeg (если ещё нет)…"
brew list python@3.13 >/dev/null 2>&1 || brew install python@3.13
command -v ffmpeg >/dev/null 2>&1 || brew install ffmpeg
PY="$(brew --prefix python@3.13)/bin/python3.13"
ok "Python 3.13 + ffmpeg"

# 3. Скачиваю оригинальный движок + накатываю улучшения
say "Скачиваю движок (оригинал от автора) и накатываю улучшения…"
if [ ! -d "$DIR/examples" ]; then
  git clone --depth 1 https://github.com/Mobiss11/Whisper-Skill "$DIR"
fi
cd "$DIR"
if git apply --check "$HERE/improvements.patch" 2>/dev/null; then
  git apply "$HERE/improvements.patch"
  ok "Улучшения накатаны"
elif patch -p1 --forward --silent < "$HERE/improvements.patch" 2>/dev/null; then
  ok "Улучшения накатаны (fallback patch)"
else
  warn "Не удалось наложить улучшения (возможно, оригинал обновился). Базовая версия всё равно поставится."
fi

# 4. venv + зависимости
say "Создаю окружение и ставлю зависимости (пара минут)…"
[ -d "$DIR/.venv" ] || "$PY" -m venv "$DIR/.venv"
"$DIR/.venv/bin/python" -m pip install -q --upgrade pip
"$DIR/.venv/bin/pip" install -q mlx-whisper sounddevice soundfile pynput pyperclip numpy
ok "Зависимости установлены"

# 5. Конфиг
say "Пишу конфиг…"
mkdir -p "$CFG_DIR"
cat > "$CFG_DIR/voice_dictation.json" <<'JSON'
{
  "hotkey": "<alt_r>",
  "mode": "toggle",
  "language": "ru",
  "model": "large-v3-turbo",
  "backend": "mlx",
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
ok "Конфиг: правый Option, toggle, язык ru, модель large-v3-turbo"

# 6. Автозапуск (launchd)
say "Настраиваю автозапуск…"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.whisper.dictation</string>
  <key>ProgramArguments</key><array>
    <string>$DIR/.venv/bin/python</string><string>-m</string><string>examples.voice_dictation</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Interactive</string>
  <key>EnvironmentVariables</key><dict><key>PYTHONUNBUFFERED</key><string>1</string></dict>
  <key>StandardOutPath</key><string>/tmp/whisper_dictation.log</string>
  <key>StandardErrorPath</key><string>/tmp/whisper_dictation.err</string>
</dict></plist>
PLISTEOF
launchctl bootout "gui/$UID_NUM/com.whisper.dictation" 2>/dev/null || true
sleep 1
launchctl bootstrap "gui/$UID_NUM" "$PLIST" 2>/dev/null || true
ok "Автозапуск настроен"

# 7. Разрешения (две галочки — Apple требует ставить руками)
PYAPP="$("$DIR/.venv/bin/python" - <<'PYEOF'
import ctypes
b=ctypes.create_string_buffer(4096); s=ctypes.c_uint32(4096)
ctypes.CDLL(None)._NSGetExecutablePath(b, ctypes.byref(s)); print(b.value.decode())
PYEOF
)"
printf "%s" "$PYAPP" | pbcopy
say "ПОЧТИ ГОТОВО — осталось 2 галочки (Apple требует руками):"
echo "  Путь к Python СКОПИРОВАН в буфер. В каждой панели: + → Cmd+Shift+G → Cmd+V → Enter → Open → включи тумблер."
echo "    1) Универсальный доступ (Accessibility)"
echo "    2) Мониторинг ввода (Input Monitoring)"
echo "  Путь: $PYAPP"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true
sleep 2
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent" 2>/dev/null || true
say "После двух галочек диктовка заработает сама (перезапуск не нужен)."
echo "  Пользоваться: тык ПРАВОГО Option → говоришь → ещё тык → текст печатается."
echo "  Первая диктовка скачает модель (~1.6 ГБ). Из РФ HuggingFace может лимитировать —"
echo "  включи VPN на момент первого запуска или добавь бесплатный HF-токен."
ok "Готово. Можно закрыть окно."
read -r -p "Enter для выхода…" _

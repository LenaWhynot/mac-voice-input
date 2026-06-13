#!/usr/bin/env python3
"""Нативное окно «История диктовок» (Tkinter) — поиск + копирование по записи.

Читает ~/.config/whisper-skill/dictation-history.txt (строки вида
`[2026-06-13T16:42:01] текст`), показывает карточками от новых к старым,
сгруппированными по дню. Кнопка у каждой записи кладёт текст в буфер через
pbcopy (Tk-буфер очищается при закрытии окна, pbcopy — нет).
"""
import os
import re
import subprocess
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

HISTORY = os.path.expanduser("~/.config/whisper-skill/dictation-history.txt")
LINE_RE = re.compile(r"^\[(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):\d{2}\]\s?(.*)$")
MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]

# Палитра — под иконку Whispee (фиолетовый), тёплый светлый фон
BG       = "#faf9fb"   # фон окна
SURFACE  = "#f3f1f7"   # шапка / строка поиска
CARD     = "#ffffff"
BORDER   = "#ece9f1"
BORDER_H = "#d6cfe8"   # бордер карточки при наведении
TEXT     = "#1e1b2e"
MUTED    = "#8b8696"
DAYC     = "#6b6577"
ACCENT   = "#7c3aed"   # фиолетовый
ACCENT_H = "#6d28d9"
ACCENT_SOFT = "#f3eefe"  # бледно-фиолетовая подложка кнопки в покое
OK_GREEN = "#16a34a"
PLACEHOLDER = "🔍   Поиск по тексту…"


def load_entries():
    """→ list of (date_tuple(y,m,d), 'HH:MM', text), новые первыми."""
    if not os.path.exists(HISTORY):
        return []
    out = []
    with open(HISTORY, encoding="utf-8") as f:
        for raw in f:
            m = LINE_RE.match(raw.rstrip("\n"))
            if not m:
                continue
            y, mo, d, hh, mm, _ = m.groups()
            text = m.group(6)
            if text.strip():
                out.append(((int(y), int(mo), int(d)), f"{hh}:{mm}", text))
    out.reverse()
    return out


def day_label(dt):
    return f"{dt[2]} {MONTHS[dt[1]]} {dt[0]}"


class HistoryApp:
    def __init__(self, root):
        self.root = root
        self.entries = load_entries()
        self._fit_after = None
        root.title("История диктовок")
        root.geometry("600x720")
        root.minsize(440, 420)
        root.configure(bg=BG)

        # ── Шрифты (системный SF на macOS; Tk сам подберёт фолбэк) ──
        self.f_title = tkfont.Font(family="SF Pro Display", size=18, weight="bold")
        self.f_sub   = tkfont.Font(family="SF Pro Text", size=11)
        self.f_search= tkfont.Font(family="SF Pro Text", size=14)
        self.f_day   = tkfont.Font(family="SF Pro Text", size=11, weight="bold")
        self.f_time  = tkfont.Font(family="SF Pro Text", size=11)
        self.f_body  = tkfont.Font(family="SF Pro Text", size=13)
        self.f_btn   = tkfont.Font(family="SF Pro Text", size=11, weight="bold")

        # ── Шапка (фиксированная) ──
        header = tk.Frame(root, bg=SURFACE)
        header.pack(fill="x")
        hin = tk.Frame(header, bg=SURFACE)
        hin.pack(fill="x", padx=22, pady=(20, 4))
        tk.Label(hin, text="🎤  История диктовок", bg=SURFACE, fg=TEXT,
                 font=self.f_title).pack(anchor="w")
        self.count_lbl = tk.Label(header, bg=SURFACE, fg=MUTED, font=self.f_sub)
        self.count_lbl.pack(anchor="w", padx=22, pady=(0, 4))

        # строка поиска
        sb = tk.Frame(header, bg=SURFACE)
        sb.pack(fill="x", padx=18, pady=(6, 16))
        self.search_wrap = tk.Frame(sb, bg=CARD, highlightthickness=1,
                                    highlightbackground=BORDER, highlightcolor=ACCENT)
        self.search_wrap.pack(fill="x")
        self.query = tk.StringVar()
        self.ent = tk.Entry(self.search_wrap, textvariable=self.query,
                            font=self.f_search, relief="flat", bd=0,
                            bg=CARD, fg=MUTED, insertbackground=ACCENT,
                            highlightthickness=0)
        self.ent.pack(fill="x", padx=12, ipady=9)
        self._placeholder(self.ent, PLACEHOLDER)

        # тонкая разделительная линия под шапкой
        tk.Frame(root, bg=BORDER, height=1).pack(fill="x")

        # ── Прокручиваемая область ──
        wrap = tk.Frame(root, bg=BG)
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        style = ttk.Style()
        try:
            style.theme_use("clam")
            style.configure("Hist.Vertical.TScrollbar", background="#d8d3e2",
                            troughcolor=BG, bordercolor=BG, arrowcolor=BG,
                            relief="flat", width=8)
            style.map("Hist.Vertical.TScrollbar", background=[("active", "#c4bcd8")])
            sb_style = "Hist.Vertical.TScrollbar"
        except Exception:
            sb_style = "Vertical.TScrollbar"
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview,
                            style=sb_style)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", padx=(0, 4), pady=4)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self.win, width=e.width))
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(int(-1 * e.delta), "units"))

        # ── Тост «скопировано» ──
        self.toast = tk.Label(root, text="", bg=BG, fg=OK_GREEN, font=self.f_sub)
        self.toast.pack(fill="x", padx=22, pady=(0, 10))

        # хоткеи
        root.bind("<Escape>", lambda _: root.destroy())
        root.bind("<Command-f>", lambda _: (self.ent.focus_set(), "break"))

        self.query.trace_add("write", lambda *_: self.render())
        self.render()

    # ── placeholder для поля поиска ──
    def _placeholder(self, ent, text):
        def on_in(_):
            if ent.get() == text:
                ent.delete(0, "end"); ent.config(fg=TEXT)
        def on_out(_):
            if not ent.get():
                ent.insert(0, text); ent.config(fg=MUTED)
        ent.insert(0, text); ent.config(fg=MUTED)
        ent.bind("<FocusIn>", on_in); ent.bind("<FocusOut>", on_out)
        self._ph = text

    def _q(self):
        q = self.query.get().strip()
        return "" if q == getattr(self, "_ph", "") else q.lower()

    # ── копирование ──
    def copy(self, text, btn):
        try:
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            self.toast.config(text="✓  Скопировано в буфер — жми Cmd+V")
            btn.config(text="✓ скопировано", bg=OK_GREEN, fg="#ffffff")
            self.root.after(1500, lambda: self._reset_btn(btn))
            self.root.after(2600, lambda: self.toast.config(text=""))
        except Exception as e:
            self.toast.config(text=f"Не удалось скопировать: {e}")

    def _reset_btn(self, btn):
        try:
            btn.config(text="копировать", bg=ACCENT_SOFT, fg=ACCENT)
        except tk.TclError:
            pass

    # ── карточка с ховером ──
    def _card(self, parent, hhmm, text):
        card = tk.Frame(parent, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER)
        card.pack(fill="x", padx=14, pady=5)

        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(head, text=hhmm, bg=CARD, fg=MUTED, font=self.f_time).pack(side="left")
        btn = tk.Label(head, text="копировать", bg=ACCENT_SOFT, fg=ACCENT,
                       font=self.f_btn, padx=12, pady=3, cursor="pointinghand")
        btn.pack(side="right")
        btn.bind("<Button-1>", lambda _e, t=text, b=btn: self.copy(t, b))

        lbl = tk.Label(card, text=text, bg=CARD, fg=TEXT, justify="left",
                       font=self.f_body, wraplength=self._wrap_w(), anchor="w")
        lbl.pack(fill="x", padx=14, pady=(0, 12))
        self._wrap_labels.append(lbl)

        # ховеры
        def enter(_):
            card.config(highlightbackground=BORDER_H)
            if btn.cget("bg") == ACCENT_SOFT:
                btn.config(bg=ACCENT, fg="#ffffff")
        def leave(_):
            card.config(highlightbackground=BORDER)
            if btn.cget("bg") == ACCENT:
                btn.config(bg=ACCENT_SOFT, fg=ACCENT)
        for w in (card, head, lbl):
            w.bind("<Enter>", enter); w.bind("<Leave>", leave)
        btn.bind("<Enter>", lambda _e: btn.config(bg=ACCENT_H, fg="#ffffff"))
        btn.bind("<Leave>", lambda _e: btn.config(
            bg=ACCENT_SOFT if btn.cget("text") == "копировать" else btn.cget("bg"),
            fg=ACCENT if btn.cget("text") == "копировать" else btn.cget("fg")))
        return card

    def _wrap_w(self):
        w = self.canvas.winfo_width()
        return max(260, (w if w > 1 else 600) - 90)

    def render(self):
        if not hasattr(self, "inner"):
            return
        for w in self.inner.winfo_children():
            w.destroy()
        self._wrap_labels = []
        q = self._q()
        shown = 0
        last_day = None

        tk.Frame(self.inner, bg=BG, height=6).pack()  # верхний отступ
        for dt, hhmm, text in self.entries:
            if q and q not in text.lower():
                continue
            shown += 1
            if dt != last_day:
                last_day = dt
                tk.Label(self.inner, text=day_label(dt).upper(), bg=BG, fg=DAYC,
                         font=self.f_day).pack(anchor="w", padx=18, pady=(14, 4))
            self._card(self.inner, hhmm, text)

        total = len(self.entries)
        if not self.entries:
            self._empty("Пока нет ни одной диктовки.\nНадиктуйте что-нибудь — появится здесь.")
            self.count_lbl.config(text="")
        elif shown == 0:
            self._empty("Ничего не найдено.\nПопробуйте другой запрос.")
            self.count_lbl.config(text=f"Всего записей: {total}")
        elif q:
            self.count_lbl.config(text=f"Найдено: {shown} из {total}")
        else:
            w = "запись" if total % 10 == 1 and total % 100 != 11 else \
                "записи" if 2 <= total % 10 <= 4 and not 12 <= total % 100 <= 14 else "записей"
            self.count_lbl.config(text=f"{total} {w}")
        self.canvas.yview_moveto(0)

    def _empty(self, msg):
        box = tk.Frame(self.inner, bg=BG)
        box.pack(fill="x", pady=60)
        tk.Label(box, text="🎙", bg=BG, fg=MUTED,
                 font=tkfont.Font(size=40)).pack()
        tk.Label(box, text=msg, bg=BG, fg=MUTED, font=self.f_body,
                 justify="center").pack(pady=(8, 0))


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 2.0)
    except Exception:
        pass
    app = HistoryApp(root)
    # перевёрстка wraplength при ресайзе окна
    def on_resize(_):
        if app._fit_after:
            root.after_cancel(app._fit_after)
        app._fit_after = root.after(120, lambda: [
            l.config(wraplength=app._wrap_w()) for l in getattr(app, "_wrap_labels", [])])
    root.bind("<Configure>", on_resize)
    root.lift()
    root.attributes("-topmost", True)
    root.after(350, lambda: root.attributes("-topmost", False))
    root.mainloop()


if __name__ == "__main__":
    main()

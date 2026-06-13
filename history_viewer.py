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

HISTORY = os.path.expanduser("~/.config/whisper-skill/dictation-history.txt")
LINE_RE = re.compile(r"^\[(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):\d{2}\]\s?(.*)$")
MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]

BG = "#f5f5f4"; CARD = "#ffffff"; TEXT = "#1c1917"; MUTED = "#78716c"
ACCENT = "#facc15"; ACCENT_TX = "#1c1917"; HEADER = "#44403c"


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
        root.title("История диктовок — Whispee")
        root.geometry("560x680")
        root.minsize(420, 400)
        root.configure(bg=BG)

        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(top, text="🎤  История диктовок", bg=BG, fg=TEXT,
                 font=("SF Pro Text", 16, "bold")).pack(anchor="w")
        self.count_lbl = tk.Label(top, text="", bg=BG, fg=MUTED,
                                  font=("SF Pro Text", 11))
        self.count_lbl.pack(anchor="w", pady=(2, 0))

        sb = tk.Frame(root, bg=BG)
        sb.pack(fill="x", padx=16, pady=(0, 8))
        self.query = tk.StringVar()
        ent = tk.Entry(sb, textvariable=self.query, font=("SF Pro Text", 13),
                       relief="flat", bg="#ffffff", fg=TEXT,
                       highlightthickness=1, highlightbackground="#e7e5e4",
                       highlightcolor=ACCENT)
        ent.pack(fill="x", ipady=7)
        self._placeholder(ent, "🔍  Поиск по тексту…")

        # Прокручиваемая область
        wrap = tk.Frame(root, bg=BG)
        wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self.win, width=e.width))
        # Прокрутка колесом/тачпадом
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(int(-1 * (e.delta)), "units"))

        self.toast = tk.Label(root, text="", bg=BG, fg="#16a34a",
                              font=("SF Pro Text", 11))
        self.toast.pack(fill="x", padx=16, pady=(0, 8))

        # Трейс вешаем ПОСЛЕ сборки всех виджетов — иначе placeholder-insert
        # дёрнет render() до создания списка.
        self.query.trace_add("write", lambda *_: self.render())
        self.render()

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

    def copy(self, text, btn):
        try:
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            self.toast.config(text="✓ Скопировано в буфер — жми Cmd+V")
            btn.config(text="✓ скопировано")
            self.root.after(1600, lambda: btn.config(text="⧉ копировать"))
            self.root.after(2600, lambda: self.toast.config(text=""))
        except Exception as e:
            self.toast.config(text=f"Не удалось скопировать: {e}")

    def render(self):
        if not hasattr(self, "inner"):
            return
        for w in self.inner.winfo_children():
            w.destroy()
        q = self._q()
        shown = 0
        last_day = None
        for dt, hhmm, text in self.entries:
            if q and q not in text.lower():
                continue
            shown += 1
            if dt != last_day:
                last_day = dt
                tk.Label(self.inner, text=day_label(dt), bg=BG, fg=HEADER,
                         font=("SF Pro Text", 12, "bold")).pack(
                    anchor="w", padx=12, pady=(12, 4))
            card = tk.Frame(self.inner, bg=CARD, highlightthickness=1,
                            highlightbackground="#e7e5e4")
            card.pack(fill="x", padx=8, pady=4)
            head = tk.Frame(card, bg=CARD)
            head.pack(fill="x", padx=10, pady=(8, 2))
            tk.Label(head, text=hhmm, bg=CARD, fg=MUTED,
                     font=("SF Pro Text", 11)).pack(side="left")
            btn = tk.Button(head, text="⧉ копировать", relief="flat",
                            bg=ACCENT, fg=ACCENT_TX, font=("SF Pro Text", 11),
                            activebackground="#eab308", cursor="pointinghand",
                            padx=10, pady=1, bd=0, highlightthickness=0)
            btn.config(command=lambda t=text, b=btn: self.copy(t, b))
            btn.pack(side="right")
            lbl = tk.Label(card, text=text, bg=CARD, fg=TEXT, justify="left",
                           font=("SF Pro Text", 13), wraplength=480, anchor="w")
            lbl.pack(fill="x", padx=10, pady=(0, 10))

        total = len(self.entries)
        if not self.entries:
            tk.Label(self.inner, text="Пока нет ни одной диктовки.\nНадиктуйте что-нибудь — появится здесь.",
                     bg=BG, fg=MUTED, font=("SF Pro Text", 13), justify="center").pack(pady=40)
            self.count_lbl.config(text="")
        elif q:
            self.count_lbl.config(text=f"Найдено: {shown} из {total}")
        else:
            self.count_lbl.config(text=f"Всего записей: {total}")
        self.canvas.yview_moveto(0)


def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 2.0)
    except Exception:
        pass
    HistoryApp(root)
    root.lift()
    root.attributes("-topmost", True)
    root.after(300, lambda: root.attributes("-topmost", False))
    root.mainloop()


if __name__ == "__main__":
    main()

"""Statistik hisobot tekshiruvchi — Windows oynasi (tkinter).

Ma'lumotnomalar (nazoratlar va reyestr) dastur yonidagi `malumotnomalar/` papkasida saqlanadi,
har bir yangilashda eski versiya `malumotnomalar/arxiv/` ga ko'chiriladi.
Natijalar `Natijalar/` papkasiga yoziladi.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if getattr(sys, "frozen", False):          # PyInstaller .exe
    APP_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR = BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BUNDLE_DIR)

from checker import list_reports, load_registry, run  # noqa: E402
from engine import RuleSet  # noqa: E402

VERSION = "1.0"
DATA_DIR = os.path.join(APP_DIR, "malumotnomalar")
ARCHIVE_DIR = os.path.join(DATA_DIR, "arxiv")
RESULT_DIR = os.path.join(APP_DIR, "Natijalar")
CONFIG = os.path.join(DATA_DIR, "sozlamalar.json")

BLUE = "#1a4f8a"
BG = "#eef2f8"
COLORS = {"Xatosiz": ("#067647", "#e7f6ee"), "Xatoli": ("#b42318", "#fdecea"),
          "To'liq emas": ("#93370d", "#fef3e2"), "Ochilmadi": ("#3d4a60", "#eceff4")}


def open_path(p):
    try:
        if sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Xato", f"Ochib bo'lmadi:\n{p}\n\n{e}")


# ------------------------------------------------------------ ma'lumotnomalar

class Store:
    """Joriy nazoratlar/reyestr fayllari va ularning arxivi."""

    KINDS = {"nazoratlar": "Mantiqiy nazoratlar", "reyestr": "Reyestr"}

    def __init__(self):
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        os.makedirs(RESULT_DIR, exist_ok=True)
        self.cfg = {}
        if os.path.exists(CONFIG):
            try:
                with open(CONFIG, encoding="utf-8") as f:
                    self.cfg = json.load(f)
            except (OSError, ValueError):
                self.cfg = {}
        # Birinchi ishga tushishda dastur bilan kelgan nazoratlar faylini ko'chiramiz
        if not self.current("nazoratlar"):
            src = os.path.join(BUNDLE_DIR, "nazoratlar.xlsx")
            if os.path.exists(src):
                try:
                    rs = RuleSet.load(src)
                    summ = f"{sum(len(v) for v in rs.rules.values())} nazorat, {len(rs.forms)} shakl"
                except Exception:  # noqa: BLE001
                    summ = ""
                self._install("nazoratlar", src, note="Dastur bilan kelgan", summary=summ)

    def save(self):
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False, indent=1)

    def current(self, kind):
        info = self.cfg.get(kind)
        if info and os.path.exists(os.path.join(DATA_DIR, info["file"])):
            return info
        return None

    def path(self, kind):
        info = self.current(kind)
        return os.path.join(DATA_DIR, info["file"]) if info else None

    def history(self, kind):
        return self.cfg.get(kind + "_tarix", [])

    def _install(self, kind, src, note="", summary=""):
        ext = os.path.splitext(src)[1].lower()
        old = self.current(kind)
        if old:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            arch = f"{kind}_{stamp}{os.path.splitext(old['file'])[1]}"
            shutil.move(os.path.join(DATA_DIR, old["file"]), os.path.join(ARCHIVE_DIR, arch))
            old = dict(old, file=os.path.join("arxiv", arch))
            self.cfg.setdefault(kind + "_tarix", []).insert(0, old)
        name = f"{kind}{ext}"
        shutil.copy2(src, os.path.join(DATA_DIR, name))
        n = len(self.history(kind)) + 1
        self.cfg[kind] = {"file": name, "source": os.path.basename(src), "date": time.strftime("%d.%m.%Y %H:%M"),
                          "version": n, "summary": summary, "note": note}
        self.save()

    def install(self, kind, src, summary=""):
        self._install(kind, src, summary=summary)

    def restore(self, kind, idx):
        h = self.history(kind)[idx]
        src = os.path.join(DATA_DIR, h["file"])
        tmp = os.path.join(DATA_DIR, "_restore" + os.path.splitext(src)[1])
        shutil.copy2(src, tmp)
        self._install(kind, tmp, note=f"v{h['version']} dan qaytarildi", summary=h.get("summary", ""))
        self.cfg[kind]["source"] = h.get("source", "")
        self.save()
        os.remove(tmp)


def describe_rules(path):
    rs = RuleSet.load(path)
    rules = [r for v in rs.rules.values() for r in v]
    bad = []
    for r in rules:
        try:
            r.parse()
        except ValueError as e:
            if r.active:
                bad.append(f"{r.form}-SSV {r.section}-bo'lim №{r.code}: {e}")
    keys = {(r.form, r.section, r.code, r.shifr, r.active) for r in rules}
    return rs, rules, bad, keys


def compare_rules(old_path, new_path):
    rs, rules, bad, new_keys = describe_rules(new_path)
    lines = [f"✓ {len(rs.forms)} ta shakl, {len(rules)} ta nazorat o'qildi "
             f"({sum(r.active for r in rules)} tasi faol)"]
    if not rs.forms:
        lines.append("✕ 'Formalar' varag'i bo'sh yoki topilmadi")
    if rs.empty_shifr:
        ex = ", ".join(f"{f}-SSV {sec}/{k}" for f, sec, k in rs.empty_shifr[:5])
        bad = [f"{len(rs.empty_shifr)} ta qatorda Shifr bo'sh yoki xato ({ex}…). Excelda '=' bilan boshlanadigan "
               f"shifr oldiga apostrof qo'ying: '=0R:..."] + bad
    lines += [f"✕ {b}" for b in bad[:15]]
    if len(bad) > 15:
        lines.append(f"✕ ... yana {len(bad) - 15} ta")
    diff = None
    if old_path:
        _, _, _, old_keys = describe_rules(old_path)
        oid = {k[:3] for k in old_keys}
        nid = {k[:3] for k in new_keys}
        added, removed = len(nid - oid), len(oid - nid)
        changed = len({k[:3] for k in (new_keys - old_keys)} & oid)
        diff = (added, removed, changed)
    ok = not bad and bool(rs.forms)
    return ok, lines, diff, f"{len(rules)} nazorat"


def compare_registry(old_path, new_path):
    reg = load_registry(new_path)
    lines = [f"✓ {reg.count} ta muassasa o'qildi"]
    no_forms = sum(1 for o in reg.orgs.values() if not o["forms"])
    if no_forms:
        lines.append(f"! {no_forms} ta muassasada topshiradigan shakli belgilanmagan")
    diff = None
    if old_path:
        old = load_registry(old_path)
        a, b = set(reg.orgs), set(old.orgs)
        changed = sum(1 for s in a & b if reg.orgs[s] != old.orgs[s])
        diff = (len(a - b), len(b - a), changed)
    return reg.count > 0, lines, diff, f"{reg.count} muassasa"


# --------------------------------------------------------------------- oyna

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Statistik hisobot tekshiruvchi v{VERSION}")
        self.geometry("1100x720")
        self.minsize(900, 620)
        self.configure(bg=BG)
        self.store = Store()
        self.q: queue.Queue = queue.Queue()
        self.worker = None
        self.stop_flag = False
        self.last_result = None
        self._style()
        self._build()
        self.refresh_refs()
        self.folder.set(self.store.cfg.get("papka", ""))
        self.count_files()
        self.after(100, self._poll)

    # ----------------------------------------------------------- ko'rinish
    def _style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", font=("Segoe UI", 10), background=BG)
        s.configure("Card.TFrame", background="white", relief="solid", borderwidth=1)
        s.configure("Card.TLabel", background="white")
        s.configure("Muted.TLabel", background="white", foreground="#55627a", font=("Segoe UI", 9))
        s.configure("Head.TLabel", background="white", font=("Segoe UI", 10, "bold"))
        s.configure("Title.TLabel", background=BG, font=("Segoe UI", 16, "bold"))
        s.configure("Sub.TLabel", background=BG, foreground="#55627a")
        s.configure("Ok.TLabel", background="white", foreground="#067647")
        s.configure("Bad.TLabel", background="white", foreground="#b42318")
        s.configure("Card.TCheckbutton", background="white")
        s.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=10, foreground="white", background=BLUE)
        s.map("Big.TButton", background=[("disabled", "#9fb0c8"), ("active", "#0f3a6a")])
        s.configure("Horizontal.TProgressbar", troughcolor="#e3e8f1", background=BLUE, thickness=14)

    def _card(self, parent, title):
        f = ttk.Frame(parent, style="Card.TFrame", padding=12)
        ttk.Label(f, text=title, style="Head.TLabel").pack(anchor="w", pady=(0, 6))
        return f

    def _build(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        left = ttk.Frame(root, width=470)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        right = ttk.Frame(root)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))

        ttk.Label(left, text="Yillik hisobotlarni tekshirish", style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="DMED orqali qabul qilingan SSV fayllarini mantiqiy nazoratlar bo'yicha tekshiradi.",
                  style="Sub.TLabel", wraplength=470).pack(anchor="w", pady=(2, 10))

        c1 = self._card(left, "1. Hisobotlar papkasi")
        c1.pack(fill="x", pady=(0, 10))
        row = ttk.Frame(c1, style="Card.TFrame")
        row.configure(borderwidth=0)
        row.pack(fill="x")
        self.folder = tk.StringVar()
        ttk.Entry(row, textvariable=self.folder, width=10).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Tanlash…", command=self.pick_folder).pack(side="left", padx=(6, 0))
        self.files_lbl = ttk.Label(c1, text="", style="Muted.TLabel")
        self.files_lbl.pack(anchor="w", pady=(6, 0))
        self.folder.trace_add("write", lambda *_: self.count_files())

        c2 = self._card(left, "2. Ma'lumotnomalar")
        c2.pack(fill="x", pady=(0, 10))
        self.ref_lbl = {}
        for kind in ("reyestr", "nazoratlar"):
            r = ttk.Frame(c2, style="Card.TFrame")
            r.configure(borderwidth=0)
            r.pack(fill="x", pady=3)
            ttk.Button(r, text="Yangilash…", command=lambda k=kind: UpdateDialog(self, k)).pack(side="right", padx=(8, 0))
            box = ttk.Frame(r, style="Card.TFrame")
            box.configure(borderwidth=0)
            box.pack(side="left", fill="x", expand=True)
            ttk.Label(box, text=Store.KINDS[kind], style="Card.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            lbl = ttk.Label(box, text="", style="Muted.TLabel", wraplength=320)
            lbl.pack(anchor="w")
            self.ref_lbl[kind] = lbl

        c3 = self._card(left, "3. Qo'shimcha")
        c3.pack(fill="x", pady=(0, 10))
        self.opt_missing = tk.BooleanVar(value=True)
        self.missing_cb = ttk.Checkbutton(c3, text="Reyestr bo'yicha topshirmagan muassasalarni chiqarish",
                                          variable=self.opt_missing, style="Card.TCheckbutton")
        self.missing_cb.pack(anchor="w")

        self.start_btn = ttk.Button(left, text="▶  Tekshirishni boshlash", style="Big.TButton", command=self.start)
        self.start_btn.pack(fill="x", side="bottom")

        # o'ng panel: jarayon va natija
        pc = self._card(right, "Tekshiruv")
        pc.pack(fill="both", expand=True)
        self.prog_lbl = ttk.Label(pc, text="Papkani tanlang va «Tekshirishni boshlash» tugmasini bosing.",
                                  style="Card.TLabel")
        self.prog_lbl.pack(anchor="w")
        self.prog = ttk.Progressbar(pc, mode="determinate")
        self.prog.pack(fill="x", pady=8)
        tiles = tk.Frame(pc, bg="white")
        tiles.pack(fill="x")
        self.tile = {}
        for i, key in enumerate(("Xatosiz", "Xatoli", "To'liq emas", "Ochilmadi")):
            fg, bg = COLORS[key]
            t = tk.Frame(tiles, bg=bg, padx=10, pady=8)
            t.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0 if i % 2 == 0 else 6, 0), pady=(0 if i < 2 else 6, 0))
            tiles.columnconfigure(i % 2, weight=1)
            tk.Label(t, text=key, bg=bg, fg=fg, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            v = tk.Label(t, text="0", bg=bg, fg=fg, font=("Segoe UI", 18, "bold"))
            v.pack(anchor="w")
            self.tile[key] = v
        logf = tk.Frame(pc, bg="white")
        logf.pack(fill="both", expand=True, pady=(10, 8))
        self.log = tk.Text(logf, height=10, bg="#1a2232", fg="#e6ebf3", font=("Consolas", 9), relief="flat",
                           insertbackground="white", wrap="word")
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        for tag, col in (("ok", "#6fd3a0"), ("err", "#ff8a7a"), ("warn", "#ffc46b"), ("dim", "#9fb0c8")):
            self.log.tag_configure(tag, foreground=col)
        btns = ttk.Frame(pc, style="Card.TFrame")
        btns.configure(borderwidth=0)
        btns.pack(fill="x")
        self.stop_btn = ttk.Button(btns, text="To'xtatish", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left")
        self.open_btn = ttk.Button(btns, text="Natija.xlsx ni ochish", command=self.open_result, state="disabled")
        self.open_btn.pack(side="right")
        ttk.Button(btns, text="Natijalar papkasi", command=lambda: open_path(RESULT_DIR)).pack(side="right", padx=6)

    # -------------------------------------------------------------- amallar
    def refresh_refs(self):
        for kind, lbl in self.ref_lbl.items():
            info = self.store.current(kind)
            if info:
                lbl.configure(text=f"{info['source']} · {info.get('summary') or ''} · v{info['version']}, {info['date']}",
                              style="Muted.TLabel")
            else:
                lbl.configure(text="Tanlanmagan — «Yangilash…» orqali faylni tanlang", style="Bad.TLabel")
        has_reg = bool(self.store.current("reyestr"))
        self.missing_cb.configure(state="normal" if has_reg else "disabled")

    def pick_folder(self):
        d = filedialog.askdirectory(title="Hisobotlar papkasini tanlang", initialdir=self.folder.get() or None)
        if d:
            self.folder.set(d)

    def count_files(self):
        d = self.folder.get()
        if d and os.path.isdir(d):
            n = len([p for p in list_reports([d]) if not os.path.basename(p).startswith("Natija")])
            self.files_lbl.configure(text=f"✓ {n} ta Excel fayl topildi" if n else "Bu papkada .xlsm/.xlsx fayl yo'q",
                                     style="Ok.TLabel" if n else "Bad.TLabel")
        else:
            self.files_lbl.configure(text="", style="Muted.TLabel")

    def logline(self, text, tag=None):
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")

    def start(self):
        d = self.folder.get()
        if not d or not os.path.isdir(d):
            messagebox.showwarning("Papka", "Hisobotlar papkasini tanlang.")
            return
        rules = self.store.path("nazoratlar")
        if not rules:
            messagebox.showwarning("Nazoratlar", "Mantiqiy nazoratlar fayli tanlanmagan.")
            return
        reg = self.store.path("reyestr") if self.opt_missing.get() else None
        self.store.cfg["papka"] = d
        self.store.save()
        out = os.path.join(RESULT_DIR, time.strftime("Natija_%Y%m%d_%H%M%S.xlsx"))
        self.log.delete("1.0", "end")
        for v in self.tile.values():
            v.configure(text="0")
        self.counts = dict.fromkeys(self.tile, 0)
        self.prog["value"] = 0
        self.stop_flag = False
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.open_btn.configure(state="disabled")
        self.prog_lbl.configure(text="Tekshirilmoqda…")
        self.t0 = time.time()

        def work():
            try:
                files = [p for p in list_reports([d]) if not os.path.basename(p).startswith("Natija")]
                self.q.put(("total", len(files)))
                run(files, rules, reg, out,
                    progress=lambda i, n, p, res: self.q.put(("file", i, n, p, res)),
                    stop=lambda: self.stop_flag)
                self.q.put(("done", out))
            except Exception as e:  # noqa: BLE001
                self.q.put(("fail", f"{type(e).__name__}: {e}"))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_flag = True
        self.stop_btn.configure(state="disabled")
        self.logline("To'xtatilmoqda… (shu vaqtgacha tekshirilganlar natijaga yoziladi)", "warn")

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "total":
                    self.prog["maximum"] = max(msg[1], 1)
                    self.logline(f"{msg[1]} ta fayl tekshiriladi", "dim")
                elif kind == "file":
                    _, i, n, p, res = msg
                    self.prog["value"] = i
                    st = res.status if res.status in self.counts else "Xatosiz"
                    self.counts[st] += 1
                    self.tile[st].configure(text=str(self.counts[st]))
                    left = (time.time() - self.t0) / i * (n - i)
                    self.prog_lbl.configure(text=f"{i} / {n} fayl  ·  taxminan {int(left)} soniya qoldi")
                    name = os.path.basename(p)
                    if len(name) > 40:
                        name = name[:37] + "…"
                    if res.error:
                        self.logline(f"OCHILMADI  {name} — {res.error}", "dim")
                    elif res.n_errors:
                        first = next(f for f in res.findings if f.level == "Xato")
                        self.logline(f"XATO {res.n_errors:>4}  {name} — {first.message}", "err")
                    elif res.complete is False:
                        self.logline(f"TO'LIQ EMAS {name}", "warn")
                    else:
                        self.logline(f"OK         {name}", "ok")
                elif kind == "done":
                    self.last_result = msg[1]
                    self.prog_lbl.configure(text=f"Tekshiruv yakunlandi · {time.time() - self.t0:.1f} soniya · "
                                                 f"{os.path.basename(msg[1])}")
                    self.logline(f"Natija saqlandi: {msg[1]}", "ok")
                    self._finish()
                    self.open_btn.configure(state="normal")
                elif kind == "fail":
                    self.logline(f"Xatolik: {msg[1]}", "err")
                    self.prog_lbl.configure(text="Tekshiruv xato bilan to'xtadi")
                    self._finish()
                    messagebox.showerror("Xatolik", msg[1])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _finish(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def open_result(self):
        if self.last_result:
            open_path(self.last_result)


class UpdateDialog(tk.Toplevel):
    """Reyestr yoki nazoratlar faylini yangilash: tekshirish → farqni ko'rsatish → qo'llash; tarix va qaytarish."""

    def __init__(self, app: App, kind: str):
        super().__init__(app)
        self.app, self.kind = app, kind
        self.title(f"{Store.KINDS[kind]} — yangilash")
        self.geometry("620x560")
        self.configure(bg=BG)
        self.transient(app)
        self.grab_set()
        self.new_path = None
        self.summary = ""
        f = ttk.Frame(self, padding=16)
        f.pack(fill="both", expand=True)
        cur = app.store.current(kind)
        ttk.Label(f, text=Store.KINDS[kind], style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, text=(f"Joriy: {cur['source']} · {cur.get('summary', '')} · v{cur['version']}, {cur['date']}"
                           if cur else "Joriy fayl yo'q"), style="Sub.TLabel").pack(anchor="w", pady=(2, 10))
        c = app._card(f, "Yangi fayl")
        c.pack(fill="x")
        row = ttk.Frame(c, style="Card.TFrame")
        row.configure(borderwidth=0)
        row.pack(fill="x")
        self.path_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.path_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Tanlash…", command=self.pick).pack(side="left", padx=(6, 0))
        self.check_txt = tk.Text(c, height=7, bg="#f6f8fc", relief="flat", font=("Segoe UI", 9), wrap="word")
        self.check_txt.pack(fill="x", pady=(8, 0))
        self.check_txt.tag_configure("ok", foreground="#067647")
        self.check_txt.tag_configure("bad", foreground="#b42318")
        self.check_txt.tag_configure("warn", foreground="#93370d")
        self.check_txt.configure(state="disabled")
        self.diff_lbl = ttk.Label(c, text="", style="Card.TLabel")
        self.diff_lbl.pack(anchor="w", pady=(6, 0))
        b = ttk.Frame(c, style="Card.TFrame")
        b.configure(borderwidth=0)
        b.pack(fill="x", pady=(8, 0))
        self.apply_btn = ttk.Button(b, text="Qo'llash", command=self.apply, state="disabled")
        self.apply_btn.pack(side="left")
        ttk.Button(b, text="Yopish", command=self.destroy).pack(side="right")

        h = app._card(f, "Versiyalar tarixi")
        h.pack(fill="both", expand=True, pady=(12, 0))
        self.hist = tk.Listbox(h, height=6, relief="flat", font=("Segoe UI", 9))
        self.hist.pack(fill="both", expand=True)
        ttk.Button(h, text="Tanlangan versiyaga qaytarish", command=self.restore).pack(anchor="e", pady=(6, 0))
        self.fill_hist()

    def fill_hist(self):
        self.hist.delete(0, "end")
        cur = self.app.store.current(self.kind)
        if cur:
            self.hist.insert("end", f"v{cur['version']}  {cur['date']}  {cur['source']}  {cur.get('summary', '')}  — JORIY")
        for h in self.app.store.history(self.kind):
            self.hist.insert("end", f"v{h['version']}  {h['date']}  {h['source']}  {h.get('summary', '')}")

    def write(self, lines):
        self.check_txt.configure(state="normal")
        self.check_txt.delete("1.0", "end")
        for ln in lines:
            tag = "ok" if ln.startswith("✓") else "bad" if ln.startswith("✕") else "warn"
            self.check_txt.insert("end", ln + "\n", tag)
        self.check_txt.configure(state="disabled")

    def pick(self):
        types = ([("Excel", "*.xlsx")] if self.kind == "nazoratlar"
                 else [("Excel", "*.xls *.xlsx"), ("Barcha fayllar", "*.*")])
        p = filedialog.askopenfilename(parent=self, title="Yangi faylni tanlang", filetypes=types)
        if not p:
            return
        self.path_var.set(p)
        self.apply_btn.configure(state="disabled")
        self.write(["Tekshirilmoqda…"])
        self.update_idletasks()
        try:
            fn = compare_rules if self.kind == "nazoratlar" else compare_registry
            ok, lines, diff, summary = fn(self.app.store.path(self.kind), p)
        except Exception as e:  # noqa: BLE001
            self.write([f"✕ Faylni o'qib bo'lmadi: {type(e).__name__}: {e}"])
            return
        self.write(lines)
        self.diff_lbl.configure(text=(f"Joriy versiyaga nisbatan:  yangi +{diff[0]}   o'chirilgan −{diff[1]}   "
                                      f"o'zgargan {diff[2]}") if diff else "")
        self.new_path, self.summary = p, summary
        self.apply_btn.configure(state="normal" if ok else "disabled",
                                 text="Qo'llash" if ok else "Qo'llash — avval xatolarni tuzating")

    def apply(self):
        if not self.new_path:
            return
        self.app.store.install(self.kind, self.new_path, summary=self.summary)
        self.app.refresh_refs()
        self.fill_hist()
        self.apply_btn.configure(state="disabled")
        messagebox.showinfo("Yangilandi", f"{Store.KINDS[self.kind]} yangilandi. Eski versiya arxivda saqlandi.",
                            parent=self)

    def restore(self):
        sel = self.hist.curselection()
        if not sel or sel[0] == 0:
            messagebox.showinfo("Tarix", "Arxivdagi versiyalardan birini tanlang.", parent=self)
            return
        if messagebox.askyesno("Qaytarish", "Tanlangan versiyaga qaytarilsinmi? Joriy fayl arxivga o'tadi.", parent=self):
            self.app.store.restore(self.kind, sel[0] - 1)
            self.app.refresh_refs()
            self.fill_hist()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()

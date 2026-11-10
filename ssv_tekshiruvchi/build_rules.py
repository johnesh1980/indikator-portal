"""Bo'sh SSV shablonlaridan markaziy nazoratlar faylini (nazoratlar.xlsx) yasash.

Foydalanish:
    python build_rules.py <shablonlar_papkasi_yoki_fayllar...> -o nazoratlar.xlsx

Har bir shablondan olinadi:
  * '0'!A1 — shakl versiyasi, '0'!B2/C2 — shakl raqami va nomi;
  * VBA makrosdan — Tabl oralig'i (RAZDELINTERVAL), textlog oralig'i,
    textlog ustunlari tartibi va "to'liqlik sharti";
  * textlog varag'idan — nazoratlar.
Makrosning eski/yangi variantlari bitta yozuvga keltiriladi (engine.py dagi sintaksis).
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import warnings
from datetime import date

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter, range_boundaries
from oletools.olevba import VBA_Parser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Rule, TablIndex, form_number, show_code  # noqa: E402

warnings.filterwarnings("ignore")


def vba_code(path: str) -> str:
    vp = VBA_Parser(path)
    try:
        parts = [code for (_, _, _, code) in vp.extract_macros()] if vp.detect_vba_macros() else []
    finally:
        vp.close()
    lines = []
    for l in "\n".join(parts).splitlines():
        if not l.strip().startswith("'"):
            lines.append(l)
    return "\n".join(lines)


def vba_info(code: str) -> dict:
    log = re.search(r'Const LOGINTERVAL As String = "textlog!([A-Z]+\d+:[A-Z]+\d+)"', code, re.I)
    raz = re.search(r'Const RAZDELINTERVAL As String = "Tabl!([A-Z]+\d+:[A-Z]+\d+)"', code, re.I)
    idx = {}
    for var in ("razdel", "KodErr", "Shifrlog", "KolGr", "from"):
        m = re.search(rf"^\s*{var}\s*=\s*TextLog\(i,\s*(\d+)\)", code, re.M)
        if m:
            idx[var] = int(m.group(1))
    comp = ""
    m = re.search(r"If Logic\.Count = 0 Then\s*\n\s*If (.+?) Then", code)
    if m:
        expr = m.group(1)
        expr = re.sub(r'DanPerve\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*(\d+)\s*\)', r'D("\1","\2",\3)', expr)
        expr = re.sub(r"\bAnd\b", "and", expr)
        expr = re.sub(r"\bOr\b", "or", expr)
        comp = expr.strip()
    return dict(log=log.group(1) if log else None, raz=raz.group(1) if raz else None, idx=idx,
                newd="Val(Mid(Shifrlog, 2, 1))" in code, comp=comp,
                old_only=("Val(Mid(Shifrlog, 2, 1))" not in code))


def describe(section, shifr, col_from, col_to) -> str:
    r = Rule(0, section, "", shifr, col_from, col_to)
    try:
        op, minus, typ, codes = r.parse()
    except ValueError:
        return ""
    sign = "=" if op == "=" else "≥"

    def terms(xs):
        plus = xs[:len(xs) - minus] if minus else xs
        mins = xs[len(xs) - minus:] if minus else []
        return " + ".join(plus) + "".join(" − " + m for m in mins)
    if typ == "R":
        cols = f"{col_from or 1}–{col_to}" if col_to else "barcha"
        return f"{section}-bo'lim, {cols}-ustunlar: {codes[0]}-satr {sign} {terms(codes[1:])}-satr"
    if typ == "C":
        return f"{section}-bo'lim, har bir satrda: {codes[0]}-ustun {sign} {terms(codes[1:])}-ustun"
    if typ == "N":
        return f"{section}-bo'lim, {col_from}–{col_to}-ustunlar: {', '.join(codes)}-satr {sign} 0"
    if typ == "K":
        return f"{section}-bo'lim: {codes[0]}-satr {codes[1]}-ustun {sign} {codes[2]}-satr {codes[3]}-ustun"
    return ""


def normalize(shifr: str, newd: bool) -> tuple[str, str]:
    """Asl shifrni yagona yozuvga keltirish. (yangi_shifr, izoh)"""
    s = str(shifr).strip().replace(" ", "")
    if s[:1] in ("4", "5") and s[2:3] not in ("R", "C", "N"):
        return s, ""
    if re.match(r"^[=>][RCN]:", s):
        return s[0] + "0" + s[1:], f"Asl shifrda shart raqami yo'q ('{s[:3]}'), '{s[0]}0{s[1]}' deb olindi — shablonda tuzatish kerak"
    if re.match(r"^[=>]\d[RCN]:", s):
        return s, ""
    return s, f"Shifr tushunarsiz ('{s[:12]}') — shablonda tuzatish kerak"


# Haqiqiy hisobotlar bilan tekshirib aniqlangan shablon xatolari.
# (shakl, asl shifr) -> (yangi shifr yoki None = o'chirish, izoh)
OVERRIDES = {
    (2, "=3C:16:4:6:8:10:11:14:"): (
        "=3C:16:4:6:8:10:12:14:",
        "Shablonda '...10:11:14' yozilgan; juft nazorat (17 = 5+7+9−11−13−15) va haqiqiy hisobot (141 satr) "
        "bo'yicha '...10:12:14' bo'lishi kerak — tuzatildi, tasdiqlash kerak"),
}
# 12-SSV: "Oxiriga dispanserda (48–56) = Boshiga (1–9) + Olinganlar (28–36) − Chiqarilganlar (37–45)".
# Shablonda "Olinganlar" hadi tushib qolgan (=1C:48:1:37:). Foydalanuvchi 10.11.2026 da tasdiqladi.
for _i in range(9):
    OVERRIDES[(12, f"=1C:{48 + _i}:{1 + _i}:{37 + _i}:")] = (
        f"=1C:{48 + _i}:{1 + _i}:{28 + _i}:{37 + _i}:",
        f"Shablonda '{48 + _i} = {1 + _i} − {37 + _i}' yozilgan, 'Olinganlar' ({28 + _i}-ustun) tushib qolgan. "
        f"To'g'risi: Oxiriga = Boshiga + Olinganlar − Chiqarilganlar (tasdiqlangan)")
# Butun prefiks bo'yicha o'chiriladigan nazoratlar (hozircha yo'q)
DISABLE_PREFIX: dict = {}


def build(paths: list[str], out_path: str) -> None:
    seen = {}
    forms_rows, rule_rows = [], []
    for p in paths:
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        names = {n.lower().strip(): n for n in wb.sheetnames}
        s0 = wb[names["0"]]
        cover = {c.coordinate: c.value for row in s0.iter_rows(min_row=1, max_row=2, max_col=3) for c in row}
        f = form_number(cover.get("B2"))
        if f is None or f in seen:
            wb.close()
            continue
        seen[f] = p
        ver = str(cover.get("A1") or "").strip()
        title = " ".join(str(cover.get("C2") or "").split())
        info = vba_info(vba_code(p))
        notes = []
        if form_number(ver) not in (None, f):
            notes.append(f"Versiya belgisi '{ver}' boshqa shaklga tegishli")
        if not info["log"] or "textlog" not in names:
            notes.append("Shablonda mantiqiy nazorat yo'q")
            forms_rows.append([f, ver, title, info["raz"] or "E2:BZ1000", info["comp"], 0, "; ".join(notes), os.path.basename(p)])
            wb.close()
            continue

        # Tabl tuzilishi
        c1, r1, c2, r2 = range_boundaries(info["raz"])
        ncols = c2 - c1 + 1 - 2
        tabl = TablIndex()
        for row in wb[names["tabl"]].iter_rows(min_row=r1, max_row=r2, min_col=c1, max_col=c1 + 1, values_only=True):
            if row[0] not in (None, ""):
                tabl.add(row[0], row[1], {})

        # textlog: ustunlarni sarlavha bo'yicha topamiz (8-SSV dagi siljishni tuzatadi)
        lc1, lr1, lc2, lr2 = range_boundaries(info["log"])
        tl = [list(r) for r in wb[names["textlog"]].iter_rows(values_only=True)]
        hdr = {}
        for c in range(lc1, lc2 + 2):
            h = tl[0][c - 1] if c - 1 < len(tl[0]) else None
            if isinstance(h, str) and h.strip() not in hdr:
                hdr[h.strip()] = c
        ix = info["idx"]
        off = hdr["MemoShifr"] - (lc1 + ix["Shifrlog"] - 1) if "MemoShifr" in hdr and "Shifrlog" in ix else 0
        if off:
            notes.append("Makros textlog ustunlarini noto'g'ri o'qiydi (shablonda barcha nazoratlar ishlamaydi)")
        n = 0
        for r in range(2, len(tl) + 1):
            def get(k):
                # Avval textlog sarlavhasi bo'yicha (8-SSV dagi siljishni to'g'ri o'qiydi), bo'lmasa makros tartibida
                hname = {"razdel": "KodTabl", "KodErr": "KodErr", "Shifrlog": "MemoShifr",
                         "KolGr": "KolGr" if "KolGr" in hdr else "to", "from": "from"}[k]
                if hname in hdr:
                    c = hdr[hname]
                elif k in ix:
                    c = lc1 + ix[k] - 1 + off
                else:
                    return None
                row = tl[r - 1]
                return row[c - 1] if c - 1 < len(row) else None
            sec, kod, shifr = get("razdel"), get("KodErr"), get("Shifrlog")
            if shifr in (None, ""):
                continue
            kolgr, frm = get("KolGr"), get("from")
            sec_s = show_code(sec)
            new, note = normalize(shifr, info["newd"])
            izoh = [note] if note else []
            active = not note.startswith("Shifr tushunarsiz")
            if (f, new) in OVERRIDES:
                fixed, why = OVERRIDES[(f, new)]
                izoh.append(why)
                if fixed is None:
                    active = False
                else:
                    new = fixed
            for (pf, prefix), why in DISABLE_PREFIX.items():
                if pf == f and new.startswith(prefix):
                    izoh.append(why)
                    active = False
            try:
                col_to = int(float(kolgr)) if kolgr not in (None, "") else None
            except ValueError:
                col_to = None
            try:
                col_from = int(float(frm)) if frm not in (None, "") else None
            except ValueError:
                col_from = None
            typ = new[2:3]
            if not tabl.has_section(sec_s):
                izoh.append(f"{sec_s}-bo'lim Tabl varag'ida yo'q — shablonda tuzatish kerak")
                active = False
            elif typ in ("R", "N"):
                codes = [c for c in new[4:].split(":") if c]
                miss = [c for c in codes if not tabl.has_row(sec_s, c)]
                if miss:
                    izoh.append(f"Satr kodlari Tabl'da yo'q: {', '.join(miss)} (0 deb olinadi)")
            if typ == "R" and col_to is None:
                izoh.append("Ustunlar soni (KolGr) ko'rsatilmagan — 'Ustun gacha' ni to'ldiring")
                active = False
            if typ == "C":
                bad = [c for c in new[4:].split(":") if c and (not c.isdigit() or int(c) > ncols)]
                if bad:
                    izoh.append(f"Ustun raqamlari Tabl'dan tashqarida: {', '.join(bad)}")
                    active = False
            if info["old_only"] and re.match(r"^=[1-9]", new):
                izoh.append("Shablondagi eski makros bu nazoratni bajarmaydi (dastur bajaradi)")
            rule_rows.append([f, sec_s, show_code(kod) if kod is not None else "", new, col_from, col_to,
                              "Xato", "Ha" if active else "Yo'q",
                              describe(sec_s, new, col_from, col_to), str(shifr).strip(), "; ".join(izoh)])
            n += 1
        forms_rows.append([f, ver, title, info["raz"], info["comp"], n, "; ".join(notes), os.path.basename(p)])
        wb.close()

    forms_rows.sort(key=lambda r: r[0])
    rule_rows.sort(key=lambda r: r[0])

    out = openpyxl.Workbook()
    H, HF = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1A4F8A")
    GRAY = PatternFill("solid", fgColor="ECEFF4")
    ORA = PatternFill("solid", fgColor="FEF3E2")

    def sheet(ws, header, rows, widths):
        ws.append(header)
        for c in ws[1]:
            c.font, c.fill = H, HF
            c.alignment = Alignment(wrap_text=True, vertical="center")
        for r in rows:
            ws.append(r)
        for row_ in ws.iter_rows(min_row=2):
            for c in row_:
                if isinstance(c.value, str) and c.value.startswith("="):
                    c.data_type = "s"   # '=0R:...' formula emas, matn
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    ws = out.active
    ws.title = "Nazoratlar"
    sheet(ws, ["Forma", "Bo'lim", "Xato kodi", "Shifr", "Ustun dan", "Ustun gacha", "Darajasi", "Faol",
               "Tavsif", "Asl shifr (shablondagi)", "Izoh"],
          rule_rows, [8, 9, 9, 38, 10, 11, 13, 7, 70, 38, 70])
    for row in ws.iter_rows(min_row=2):
        if row[7].value == "Yo'q":
            for c in row:
                c.fill = GRAY
        elif row[10].value:
            for c in row:
                c.fill = ORA

    ws = out.create_sheet("Formalar")
    sheet(ws, ["Forma", "Versiya", "Nomi", "Tabl oralig'i", "To'liqlik sharti", "Nazoratlar", "Izoh", "Shablon fayli"],
          forms_rows, [8, 10, 60, 14, 60, 11, 60, 36])

    ws = out.create_sheet("Yo'riqnoma")
    for line in [
        ["Nazoratlar fayli — qanday tahrirlanadi"],
        [f"Yaratilgan: {date.today():%d.%m.%Y}, {len(forms_rows)} ta shakl, {len(rule_rows)} ta nazorat."],
        [""],
        ["Shifr", "<shart><ayirish><tur>:<kod1>:<kod2>:...:"],
        ["shart", "'=' — teng bo'lishi kerak; '>' — katta yoki teng bo'lishi kerak"],
        ["ayirish", "oxirgi nechta had ayiriladi (0 — hammasi qo'shiladi)"],
        ["tur", "R — satrlar (har bir ustunda), C — ustunlar (har bir satrda), N — satr 0 bilan solishtiriladi"],
        ["Misol", "=0R:19:1:2:3:   →  19-satr = 1 + 2 + 3-satrlar (Ustun dan..gacha oralig'idagi har bir ustunda)"],
        ["Misol", "=1C:4:1:2:3:    →  4-ustun = 1 + 2 − 3-ustunlar (bo'limning har bir satrida)"],
        ["Misol", ">0C:1:2:        →  1-ustun ≥ 2-ustun"],
        [""],
        ["Faol", "'Yo'q' — nazorat vaqtincha o'chirilgan (kulrang qatorlar: shablonda xato borligi uchun o'chirilgan)"],
        ["Darajasi", "'Xato' — hisobot xatoli deb belgilanadi; 'Ogohlantirish' — faqat ogohlantirish"],
        ["Formalar", "'Tabl oralig'i' — hisobotdagi yashirin Tabl varag'ining o'qiladigan qismi; "
                     "'To'liqlik sharti' — makrosdagi 'ma'lumot kiritilganmi' sharti"],
    ]:
        ws.append(line)
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 110

    out.save(out_path)
    print(f"{out_path}: {len(forms_rows)} shakl, {len(rule_rows)} nazorat, "
          f"{sum(1 for r in rule_rows if r[7] == 'Yo' + chr(39) + 'q')} tasi o'chirilgan")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("-o", "--output", default="nazoratlar.xlsx")
    a = ap.parse_args()
    paths = []
    for x in a.inputs:
        paths += sorted(glob.glob(os.path.join(x, "*.xls[mx]"))) if os.path.isdir(x) else [x]
    build(paths, a.output)


if __name__ == "__main__":
    main()

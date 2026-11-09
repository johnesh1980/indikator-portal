"""Hisobotlar papkasini tekshirish va Natija.xlsx yozish (GUI va buyruq qatori uchun umumiy).

Buyruq qatori:
    python checker.py <papka_yoki_fayllar...> -n nazoratlar.xlsx [-r reyestr.xls] [-o Natija.xlsx]
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Result, RuleSet, check_report  # noqa: E402

REPORT_EXT = (".xlsm", ".xlsx")


# ------------------------------------------------------------------ reyestr

@dataclass
class Registry:
    path: str = ""
    orgs: dict = field(default_factory=dict)      # STIR+II -> dict(name, region, district, forms:set)

    @property
    def count(self):
        return len(self.orgs)


def _clean_id(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        v = int(v)
    return re.sub(r"\.0$", "", str(v).strip())


def load_registry(path: str) -> Registry:
    """DMED reyestri (.xls yoki .xlsx). Sarlavhada 'STIR+II' ustuni va 'N-SSV' ustunlari bo'lgan varaq qidiriladi."""
    sheets = []
    if path.lower().endswith(".xls"):
        import xlrd
        book = xlrd.open_workbook(path, on_demand=True)
        for s in book.sheets():
            sheets.append((s.name, [s.row_values(r) for r in range(s.nrows)], s.nrows))
    else:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            sheets.append((ws.title, ws.iter_rows(values_only=True), ws.max_row or 0))

    best = None
    for name, rows_iter, _ in sheets:
        rows = list(rows_iter)
        stir_col = form_cols = None
        hdr_row = None
        name_col = region_col = district_col = None
        for i, row in enumerate(rows[:8]):
            cells = [str(c).strip() if c is not None else "" for c in row]
            fc = {}
            for j, c in enumerate(cells):
                m = re.fullmatch(r"(\d+)-SSV", c.replace("ССВ", "SSV"))
                if m:
                    fc[j] = int(m.group(1))
                if c.upper().startswith("STIR+") and stir_col is None:
                    stir_col, hdr_row = j, i
                if c == "Muassasa nomi" and name_col is None:
                    name_col = j
                if c.startswith("Boshqaruv hududi") and region_col is None:
                    region_col = j
                if c.startswith("Joylashgan hududi") and district_col is None:
                    district_col = j
            if len(fc) > (len(form_cols) if form_cols else 0):
                form_cols = fc
        if stir_col is None or not form_cols:
            continue
        reg = Registry(path)
        for row in rows[hdr_row + 1:]:
            stir = _clean_id(row[stir_col] if stir_col < len(row) else None)
            if not re.fullmatch(r"\d{9,14}", stir):
                continue
            forms = {f for j, f in form_cols.items() if j < len(row) and row[j] not in (None, "", 0, 0.0, "0")}
            reg.orgs[stir] = dict(
                name=str(row[name_col]).strip() if name_col is not None and name_col < len(row) else "",
                region=_clean_id(row[region_col]) if region_col is not None and region_col < len(row) else "",
                district=_clean_id(row[district_col]) if district_col is not None and district_col < len(row) else "",
                forms=forms)
        if best is None or reg.count > best.count:
            best = reg
    if best is None:
        raise ValueError("Reyestrda 'STIR+...' va 'N-SSV' ustunlari topilmadi")
    return best


# ---------------------------------------------------------------- tekshiruv

def list_reports(inputs: list[str]) -> list[str]:
    out = []
    for x in inputs:
        if os.path.isdir(x):
            for root, _, files in os.walk(x):
                for f in sorted(files):
                    if f.lower().endswith(REPORT_EXT) and not f.startswith("~$"):
                        out.append(os.path.join(root, f))
        elif x.lower().endswith(REPORT_EXT):
            out.append(x)
    return out


def run(inputs, rules_path, registry_path=None, out_path="Natija.xlsx", progress=None, stop=None):
    """progress(i, n, fayl, natija) — har bir fayldan keyin chaqiriladi; stop() True qaytarsa to'xtaydi."""
    t0 = time.time()
    ruleset = RuleSet.load(rules_path)
    registry = load_registry(registry_path) if registry_path else None
    files = list_reports(inputs)
    results: list[Result] = []
    for i, p in enumerate(files, 1):
        if stop and stop():
            break
        res = check_report(p, ruleset)
        results.append(res)
        if progress:
            progress(i, len(files), p, res)
    write_result(results, ruleset, registry, out_path, time.time() - t0)
    return results, registry


# ------------------------------------------------------------------- Excel

H, HF = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1A4F8A")
FILL = {
    "Xatosiz": PatternFill("solid", fgColor="E7F6EE"),
    "Ogohlantirish": PatternFill("solid", fgColor="FEF3E2"),
    "To'liq emas": PatternFill("solid", fgColor="FEF3E2"),
    "Xatoli": PatternFill("solid", fgColor="FDECEA"),
    "Xato": PatternFill("solid", fgColor="FDECEA"),
    "Ochilmadi": PatternFill("solid", fgColor="ECEFF4"),
    "Nazorat xatosi": PatternFill("solid", fgColor="ECEFF4"),
}


def _sheet(ws, header, rows, widths):
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
    if rows:
        ws.auto_filter.ref = ws.dimensions


def macro_verdict(res: Result) -> str:
    r = res.report
    if r.macro_ok == "1":
        return "Jo'natish mumkin"
    if r.macro_errors not in ("", "0"):
        return f"{r.macro_errors} ta xato"
    if r.macro_ok == "0":
        return "To'liq emas / tekshirilmagan"
    return ""


def write_result(results, ruleset, registry, out_path, seconds=0.0):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Xulosa"
    rows = []
    for res in results:
        r = res.report
        reg = registry.orgs.get(r.stir) if registry and r.stir else None
        if registry is None:
            reg_note = ""
        elif reg is None:
            reg_note = "Reyestrda yo'q"
        elif r.form and r.form not in reg["forms"]:
            reg_note = "Bu shaklni topshirishi belgilanmagan"
        else:
            reg_note = "Ha"
        name = (reg or {}).get("name") or r.org_name
        missed = ""
        if r.macro_ok == "1" and res.n_errors:
            missed = f"Makros {res.n_errors} ta xatoni o'tkazib yuborgan"
        rows.append([os.path.basename(r.path), r.form_label, r.stir, name, r.region_name, r.district_name, r.period,
                     r.version, {True: "Mos", False: "MOS EMAS", None: ""}[res.version_ok],
                     {True: "Ha", False: "Yo'q", None: ""}[res.complete],
                     res.status, res.n_errors, res.n_warnings,
                     sum(1 for f in res.findings if f.level == "Nazorat xatosi"),
                     macro_verdict(res), missed, reg_note, res.error])
    _sheet(ws, ["Fayl", "Shakl", "STIR", "Muassasa", "Hudud", "Tuman", "Davr", "Versiya", "Versiya mosligi",
                "Ma'lumot kiritilgan", "Holat", "Xatolar", "Ogohlantirish", "Nazorat xatolari",
                "Fayl makrosi javobi", "Taqqoslash", "Reyestrda", "Ochilmaslik sababi"],
           rows, [34, 14, 13, 40, 22, 20, 20, 9, 10, 11, 13, 9, 9, 10, 22, 32, 18, 40])
    for row in ws.iter_rows(min_row=2):
        st = row[10].value
        if st in FILL:
            row[10].fill = FILL[st]
        if row[15].value:
            row[15].fill = FILL["Xato"]
        if row[8].value == "MOS EMAS":
            row[8].fill = FILL["Ogohlantirish"]

    ws = wb.create_sheet("Xatolar")
    rows = []
    for res in results:
        r = res.report
        for f in res.findings:
            rows.append([os.path.basename(r.path), r.form_label, r.stir, r.district_name, f.level, f.section, f.code,
                         f.where, f.message, f.left, f.right,
                         (f.left - f.right) if f.left is not None and f.right is not None else None, f.shifr])
    _sheet(ws, ["Fayl", "Shakl", "STIR", "Tuman", "Daraja", "Bo'lim", "Nazorat kodi", "Joyi", "Tavsif",
                "Chap qiymat", "O'ng qiymat", "Farq", "Shifr"],
           rows, [30, 14, 13, 18, 14, 8, 9, 10, 95, 11, 11, 10, 34])
    for row in ws.iter_rows(min_row=2):
        if row[4].value in FILL:
            row[4].fill = FILL[row[4].value]

    ws = wb.create_sheet("Eng ko'p xatolar")
    cnt = Counter()
    for res in results:
        for f in res.findings:
            if f.level == "Xato":
                cnt[(res.report.form_label, f.section, f.code, f.shifr)] += 1
    _sheet(ws, ["Shakl", "Bo'lim", "Nazorat kodi", "Shifr", "Necha marta buzilgan"],
           [list(k) + [v] for k, v in cnt.most_common()], [14, 9, 11, 40, 18])

    if registry:
        submitted = {}
        for res in results:
            if res.report.form and res.report.stir:
                submitted.setdefault(res.report.form, set()).add(res.report.stir)
        ws = wb.create_sheet("Topshirmaganlar")
        rows = []
        for form in sorted(submitted):
            for stir, o in sorted(registry.orgs.items(), key=lambda kv: (kv[1]["region"], kv[1]["name"])):
                if form in o["forms"] and stir not in submitted[form]:
                    rows.append([f"{form}-SSV", stir, o["name"], o["region"], o["district"]])
        _sheet(ws, ["Shakl", "STIR+II", "Muassasa", "Boshqaruv hududi (MHOBT)", "Joylashgan hududi (MHOBT)"],
               rows, [10, 14, 70, 14, 14])

    ws = wb.create_sheet("Ma'lumot")
    st = Counter(r.status for r in results)
    for line in [["Tekshiruv natijasi"], [""],
                 ["Fayllar", len(results)], ["Xatosiz", st.get("Xatosiz", 0)], ["Xatoli", st.get("Xatoli", 0)],
                 ["Ma'lumot to'liq emas", st.get("To'liq emas", 0)], ["Ochilmadi", st.get("Ochilmadi", 0)],
                 [""], ["Nazoratlar", f"{sum(len(v) for v in ruleset.rules.values())} ta, {len(ruleset.forms)} ta shakl"],
                 ["Reyestr", f"{registry.count} ta muassasa" if registry else "tanlanmagan"],
                 ["Vaqt", f"{seconds:.1f} soniya"], ["Sana", time.strftime("%d.%m.%Y %H:%M")]]:
        ws.append(line)
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 40
    wb.save(out_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="hisobotlar papkasi yoki fayllar")
    ap.add_argument("-n", "--nazoratlar", required=True)
    ap.add_argument("-r", "--reyestr")
    ap.add_argument("-o", "--output", default="Natija.xlsx")
    a = ap.parse_args()

    def prog(i, n, p, res):
        print(f"[{i}/{n}] {os.path.basename(p)}: {res.status} (xato {res.n_errors})"
              + (f" — {res.error}" if res.error else ""))
    results, reg = run(a.inputs, a.nazoratlar, a.reyestr, a.output, prog)
    print(f"Natija: {a.output}")


if __name__ == "__main__":
    main()

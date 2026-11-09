"""SSV statistik hisobotlarini mantiqiy nazoratlar bo'yicha tekshirish yadrosi.

Hisobot fayli (.xlsm) makrossiz o'qiladi: '0' varag'idan muqova ma'lumotlari,
yashirin 'Tabl' varag'idan raqamlar (Excel saqlagan qiymatlar) olinadi.
Nazoratlar markaziy `nazoratlar.xlsx` faylidan yuklanadi.

Shifr sintaksisi (SSV shakllaridagi textlog bilan bir xil, yangi makros varianti):
    <shart><ayirish><tur>:<kod1>:<kod2>:...
    shart  : '=' teng bo'lishi kerak, '>' katta yoki teng bo'lishi kerak
    ayirish: oxirgi nechta had ayiriladi (0 — hammasi qo'shiladi)
    tur    : R — satrlar (har bir ustunda), C — ustunlar (har bir satrda),
             N — sanab o'tilgan satrlar 0 bilan solishtiriladi
    Masalan: '=0R:19:1:2:3:'  -> 19-satr = 1 + 2 + 3-satrlar
             '=1C:4:1:2:3:'   -> 4-ustun = 1 + 2 − 3-ustunlar
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field

import openpyxl
from openpyxl.utils import range_boundaries

warnings.filterwarnings("ignore")

EPS = 1e-6


def norm_code(v) -> str:
    """Bo'lim/satr kodini solishtirish uchun normallashtirish ('1', 1.0, '1.0' -> '1.0')."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return repr(float(v))
    s = str(v).strip()
    try:
        return repr(float(s))
    except ValueError:
        return s


def show_code(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def fmt_num(x: float) -> str:
    if abs(x - round(x)) < EPS:
        return f"{int(round(x)):,}".replace(",", " ")
    return f"{x:,.2f}".replace(",", " ")


def form_number(text) -> int | None:
    m = re.match(r"\s*(\d+)", str(text or ""))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- nazoratlar

@dataclass
class Rule:
    form: int
    section: str
    code: str
    shifr: str
    col_from: int | None = None
    col_to: int | None = None
    level: str = "Xato"          # 'Xato' yoki 'Ogohlantirish'
    active: bool = True
    note: str = ""

    def parse(self):
        s = self.shifr.strip()
        if s[:1] in ("4", "5") and s[2:3] not in ("R", "C", "N"):
            # 15/12-SSV dagi alohida katak nazorati: '4:satr:ustun:satr:ustun:'
            parts = [p for p in s[2:].split(":") if p]
            return ("=" if s[0] == "4" else ">"), 0, "K", parts
        op, minus, typ = s[0:1], s[1:2], s[2:3]
        if op not in ("=", ">") or not minus.isdigit() or typ not in ("R", "C", "N"):
            raise ValueError(f"Shifr tushunarsiz: '{s}'")
        codes = [p for p in s[4:].split(":") if p != ""]
        if not codes:
            raise ValueError(f"Shifrda kodlar yo'q: '{s}'")
        return op, int(minus), typ, codes


@dataclass
class FormSpec:
    form: int
    version: str
    title: str
    tabl_range: str               # masalan 'E2:AB652'
    completeness: str = ""        # masalan 'D("1.0","26.0",1) > 0 and D("1.0","26.0",3) > 0'


@dataclass
class RuleSet:
    forms: dict[int, FormSpec] = field(default_factory=dict)
    rules: dict[int, list[Rule]] = field(default_factory=dict)
    empty_shifr: list = field(default_factory=list)   # (forma, bo'lim, kod) — shifr bo'sh/formula bo'lib qolgan

    @classmethod
    def load(cls, path: str) -> "RuleSet":
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rs = cls()
        fs = wb["Formalar"]
        hdr = None
        for row in fs.iter_rows(values_only=True):
            if hdr is None:
                hdr = {str(h).strip(): i for i, h in enumerate(row) if h}
                continue
            g = lambda k: row[hdr[k]] if k in hdr and hdr[k] < len(row) else None
            f = form_number(g("Forma"))
            if f is None:
                continue
            rs.forms[f] = FormSpec(f, str(g("Versiya") or ""), str(g("Nomi") or ""),
                                   str(g("Tabl oralig'i") or ""), str(g("To'liqlik sharti") or ""))
        ns = wb["Nazoratlar"]
        hdr = None
        for row in ns.iter_rows(values_only=True):
            if hdr is None:
                hdr = {str(h).strip(): i for i, h in enumerate(row) if h}
                continue
            g = lambda k: row[hdr[k]] if k in hdr and hdr[k] < len(row) else None
            f = form_number(g("Forma"))
            if f is None:
                continue
            if not g("Shifr") or str(g("Shifr")).startswith("#"):
                rs.empty_shifr.append((f, show_code(g("Bo'lim") or ""), show_code(g("Xato kodi") or "")))
                continue

            def as_int(v):
                try:
                    return int(float(v))
                except (TypeError, ValueError):
                    return None
            r = Rule(f, show_code(g("Bo'lim")), show_code(g("Xato kodi") or ""), str(g("Shifr")).strip(),
                     as_int(g("Ustun dan")), as_int(g("Ustun gacha")),
                     str(g("Darajasi") or "Xato").strip() or "Xato",
                     str(g("Faol") or "Ha").strip().lower() not in ("yo'q", "yoq", "нет", "0", "false"),
                     str(g("Izoh") or ""))
            rs.rules.setdefault(f, []).append(r)
        return rs


# ------------------------------------------------------------------ Tabl indeksi

def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def raw_key(v):
    """Tabl katagining kaliti: son kataklar son sifatida, matnlar aynan matn sifatida.
    ('15.10' va '15.1' — boshqa-boshqa satrlar; makros ham ularni matn sifatida solishtiradi.)"""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return ("n", float(v))
    return ("s", "" if v is None else str(v).strip())


class TablIndex:
    """Bo'lim/satr kodlarini VBA makrosi kabi topish:
    bo'lim — avval aynan matn, keyin son qiymati bo'yicha (textlog'da bo'lim ko'pincha son);
    satr kodi — avval aynan matn, keyin faqat son kataklar orasidan (shifrdagi kodlar doim matn)."""

    def __init__(self):
        self.rows = {}
        self.section_rows = {}
        self._sec_cache = {}

    def add(self, sec, code, vals):
        key = (raw_key(sec), raw_key(code))
        if key not in self.rows:          # makros kabi: birinchi mos satr olinadi
            self.rows[key] = vals
            self.section_rows.setdefault(key[0], []).append(key[1])

    def resolve_section(self, q):
        q = str(q).strip()
        if q in self._sec_cache:
            return self._sec_cache[q]
        k = ("s", q)
        if k not in self.section_rows:
            f = _to_float(q)
            k = None
            if f is not None:
                for cand in self.section_rows:
                    if (cand[0] == "n" and cand[1] == f) or (cand[0] == "s" and _to_float(cand[1]) == f):
                        k = cand
                        break
        self._sec_cache[q] = k
        return k

    def resolve_code(self, seck, q):
        q = str(q).strip()
        if (seck, ("s", q)) in self.rows:
            return ("s", q)
        f = _to_float(q)
        if f is not None and (seck, ("n", f)) in self.rows:
            return ("n", f)
        return None

    def value(self, sec, code, col) -> float:
        seck = self.resolve_section(sec)
        if seck is None:
            return 0.0
        ck = self.resolve_code(seck, code)
        if ck is None:
            return 0.0
        v = self.rows[(seck, ck)].get(col)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0

    def has_section(self, sec) -> bool:
        return self.resolve_section(sec) is not None

    def has_row(self, sec, code) -> bool:
        seck = self.resolve_section(sec)
        return seck is not None and self.resolve_code(seck, code) is not None

    def codes_in(self, sec):
        seck = self.resolve_section(sec)
        return [] if seck is None else self.section_rows[seck]

    @staticmethod
    def label(key) -> str:
        return show_code(key[1]) if key[0] == "n" else key[1]


# ------------------------------------------------------------------ hisobot

@dataclass
class Report:
    path: str
    form: int | None = None
    form_label: str = ""
    version: str = ""
    stir: str = ""
    region_code: str = ""
    region_name: str = ""
    district_code: str = ""
    district_name: str = ""
    org_name: str = ""
    period: str = ""
    macro_errors: str = ""        # '0'!B1 — fayl makrosi topgan xatolar soni
    macro_ok: str = ""            # '0'!C1 — 1 bo'lsa makros "jo'natish mumkin" degan
    tabl: TablIndex = field(default_factory=TablIndex)
    ncols: int = 0

    def value(self, section, code, col: int) -> float:
        return self.tabl.value(section, code, col)

    def has_row(self, section, code) -> bool:
        return self.tabl.has_row(section, code)

    def has_section(self, section) -> bool:
        return self.tabl.has_section(section)


def read_report(path: str, ruleset: RuleSet) -> Report:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    names = {n.lower().strip(): n for n in wb.sheetnames}
    if "0" not in names or "tabl" not in names:
        raise ValueError("SSV shakli emas: '0' yoki 'Tabl' varag'i topilmadi")
    s0 = wb[names["0"]]
    cover = {}
    for r_i, row in enumerate(s0.iter_rows(min_row=1, max_row=7, max_col=4, values_only=True), 1):
        for c_i, v in enumerate(row):
            cover[f"{'ABCD'[c_i]}{r_i}"] = v
    rep = Report(path)
    rep.form_label = " ".join(str(cover.get("B2") or "").split())
    rep.form = form_number(cover.get("B2"))
    rep.version = str(cover.get("A1") or "").strip()
    rep.stir = re.sub(r"\.0$", "", str(cover.get("B5") or "").strip())
    rep.region_code = re.sub(r"\.0$", "", str(cover.get("B3") or ""))
    rep.region_name = str(cover.get("C3") or "")
    rep.district_code = re.sub(r"\.0$", "", str(cover.get("B4") or ""))
    rep.district_name = str(cover.get("C4") or "")
    rep.org_name = str(cover.get("C5") or "") if not str(cover.get("C5") or "").startswith("#") else ""
    rep.period = str(cover.get("C6") or "")
    rep.macro_errors = str(cover.get("B1") if cover.get("B1") is not None else "")
    rep.macro_ok = str(cover.get("C1") if cover.get("C1") is not None else "")

    spec = ruleset.forms.get(rep.form)
    if spec and spec.tabl_range:
        c1, r1, c2, r2 = range_boundaries(spec.tabl_range)
    else:
        c1, r1, c2, r2 = 5, 2, None, None
    tb = wb[names["tabl"]]
    for row in tb.iter_rows(min_row=r1, max_row=r2, min_col=c1, max_col=c2, values_only=True):
        if not row or row[0] in (None, ""):
            continue
        vals = {g: row[g + 1] for g in range(1, len(row) - 1)}
        rep.ncols = max(rep.ncols, len(row) - 2)
        rep.tabl.add(row[0], row[1] if len(row) > 1 else None, vals)
    wb.close()
    return rep


# --------------------------------------------------------------- tekshiruv

@dataclass
class Finding:
    level: str          # 'Xato', 'Ogohlantirish', 'Nazorat xatosi'
    section: str
    code: str
    shifr: str
    where: str          # masalan '3-ustun' yoki '1.0-satr'
    message: str
    left: float | None = None
    right: float | None = None


def _terms(labels, minus):
    plus = labels[:len(labels) - minus] if minus else labels
    mins = labels[len(labels) - minus:] if minus else []
    return " + ".join(plus) + "".join(" − " + m for m in mins)


def _cmp(op, left, right) -> bool:
    return abs(left - right) <= EPS if op == "=" else left >= right - EPS


def check_rule(rep: Report, rule: Rule) -> list[Finding]:
    try:
        op, minus, typ, codes = rule.parse()
    except ValueError as e:
        return [Finding("Nazorat xatosi", rule.section, rule.code, rule.shifr, "", str(e))]
    sign = "=" if op == "=" else "≥"
    sec = rule.section
    out: list[Finding] = []
    if not rep.has_section(sec):
        return [Finding("Nazorat xatosi", sec, rule.code, rule.shifr, "",
                        f"{sec}-bo'lim hisobotning Tabl varag'ida yo'q — nazorat bajarilmadi")]
    lvl = rule.level

    if typ == "R":
        missing = [c for c in codes if not rep.has_row(sec, c)]
        if missing:
            out.append(Finding("Nazorat xatosi", sec, rule.code, rule.shifr, "",
                               f"Satr kodlari topilmadi: {', '.join(missing)} — 0 deb olindi"))
        lo = rule.col_from or 1
        hi = rule.col_to or rep.ncols
        for g in range(lo, hi + 1):
            vals = [rep.value(sec, c, g) for c in codes]
            left = vals[0]
            rv = vals[1:]
            right = sum(rv[:len(rv) - minus]) - sum(rv[len(rv) - minus:]) if minus else sum(rv)
            if not _cmp(op, left, right):
                out.append(Finding(lvl, sec, rule.code, rule.shifr, f"{g}-ustun",
                                   f"{sec}-bo'lim, {g}-ustun: {codes[0]}-satr ({fmt_num(left)}) {sign} "
                                   f"{_terms([c for c in codes[1:]], minus)}-satr ({fmt_num(right)}) bo'lishi kerak",
                                   left, right))
    elif typ == "C":
        try:
            cols = [int(c) for c in codes]
        except ValueError:
            return [Finding("Nazorat xatosi", sec, rule.code, rule.shifr, "", "Ustun raqami son emas")]
        seck = rep.tabl.resolve_section(sec)
        for ck in rep.tabl.codes_in(sec):
            row = rep.tabl.rows[(seck, ck)]
            vals = [float(row.get(g)) if isinstance(row.get(g), (int, float)) and not isinstance(row.get(g), bool)
                    else 0.0 for g in cols]
            left = vals[0]
            rv = vals[1:]
            right = sum(rv[:len(rv) - minus]) - sum(rv[len(rv) - minus:]) if minus else sum(rv)
            if not _cmp(op, left, right):
                lbl = TablIndex.label(ck)
                out.append(Finding(lvl, sec, rule.code, rule.shifr, f"{lbl}-satr",
                                   f"{sec}-bo'lim, {lbl}-satr: {cols[0]}-ustun ({fmt_num(left)}) {sign} "
                                   f"{_terms([str(c) for c in cols[1:]], minus)}-ustun ({fmt_num(right)}) bo'lishi kerak",
                                   left, right))
    elif typ == "N":
        lo = rule.col_from or 1
        hi = rule.col_to or rep.ncols
        for g in range(lo, hi + 1):
            for c in codes:
                v = rep.value(sec, c, g)
                if not _cmp(op, v, 0.0):
                    out.append(Finding(lvl, sec, rule.code, rule.shifr, f"{g}-ustun",
                                       f"{sec}-bo'lim, {g}-ustun: {c}-satr ({fmt_num(v)}) {sign} 0 bo'lishi kerak", v, 0.0))
    elif typ == "K":
        if len(codes) < 4:
            return [Finding("Nazorat xatosi", sec, rule.code, rule.shifr, "", "Katak nazorati to'liq emas")]
        a = rep.value(sec, codes[0], int(codes[1]))
        b = rep.value(sec, codes[2], int(codes[3]))
        if not _cmp(op, a, b):
            out.append(Finding(lvl, sec, rule.code, rule.shifr, "",
                               f"{sec}-bo'lim: {codes[0]}-satr {codes[1]}-ustun ({fmt_num(a)}) {sign} "
                               f"{codes[2]}-satr {codes[3]}-ustun ({fmt_num(b)}) bo'lishi kerak", a, b))
    return out


def check_completeness(rep: Report, expr: str) -> bool | None:
    """'D("1.0","26.0",1) > 0 and ...' ko'rinishidagi shartni xavfsiz hisoblash."""
    if not expr:
        return None
    tokens = re.findall(r'D\("([^"]*)",\s*"([^"]*)",\s*(\d+)\)\s*>\s*0|\b(and|or)\b|(\(|\))', expr)
    py = []
    for sec, code, col, logic, par in tokens:
        if logic:
            py.append(logic)
        elif par:
            py.append(par)
        else:
            py.append(str(rep.value(sec, code, int(col)) > 0))
    try:
        return bool(eval(" ".join(py), {"__builtins__": {}}, {}))  # faqat True/False/and/or/qavslar
    except Exception:
        return None


@dataclass
class Result:
    report: Report
    findings: list[Finding]
    complete: bool | None
    version_ok: bool | None
    error: str = ""

    @property
    def n_errors(self):
        return sum(1 for f in self.findings if f.level == "Xato")

    @property
    def n_warnings(self):
        return sum(1 for f in self.findings if f.level == "Ogohlantirish")

    @property
    def status(self):
        if self.error:
            return "Ochilmadi"
        if self.n_errors:
            return "Xatoli"
        if self.complete is False:
            return "To'liq emas"
        if self.n_warnings:
            return "Ogohlantirish"
        return "Xatosiz"


def check_report(path: str, ruleset: RuleSet) -> Result:
    try:
        rep = read_report(path, ruleset)
    except Exception as e:  # noqa: BLE001 — har qanday buzilgan fayl hisobotga yoziladi
        return Result(Report(path), [], None, None, error=f"{type(e).__name__}: {e}")
    spec = ruleset.forms.get(rep.form)
    if rep.form is None or spec is None:
        return Result(rep, [], None, None, error=f"Shakl aniqlanmadi yoki nazoratlar faylida yo'q: '{rep.form_label}'")
    findings: list[Finding] = []
    for rule in ruleset.rules.get(rep.form, []):
        if rule.active:
            findings.extend(check_rule(rep, rule))
    version_ok = (rep.version == spec.version) if spec.version else None
    return Result(rep, findings, check_completeness(rep, spec.completeness), version_ok)

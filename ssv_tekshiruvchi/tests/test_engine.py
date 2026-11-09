import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine import Report, Rule, check_completeness, check_rule  # noqa: E402


def make_report(rows):
    """rows: [(bo'lim, satr_kodi, {ustun: qiymat}), ...] — Tabl varag'idagi kabi (turi saqlanadi)."""
    rep = Report("test.xlsm", form=1)
    for sec, code, vals in rows:
        rep.tabl.add(sec, code, vals)
        rep.ncols = max(rep.ncols, max(vals) if vals else 0)
    return rep


def test_row_sum_ok_and_error():
    rep = make_report([("1.0", "1.0", {1: 10, 2: 5}), ("1.0", "1.1", {1: 6, 2: 2}), ("1.0", "1.2", {1: 4, 2: 2})])
    rule = Rule(1, "1", "7", "=0R:1.0:1.1:1.2:", 1, 2)   # bo'lim textlog'da son (1.0) bo'lgani kabi
    f = check_rule(rep, rule)
    assert len(f) == 1 and f[0].where == "2-ustun" and f[0].left == 5 and f[0].right == 4


def test_codes_15_10_and_15_1_are_different_rows():
    rep = make_report([(1, "15.0", {1: 16}), (1, "15.1", {1: 7}), (1, "15.10", {1: 9})])
    assert check_rule(rep, Rule(1, "1", "22", ">0R:15.0:15.1:15.10:", 1, 1)) == []
    rep2 = make_report([(1, "15.0", {1: 15}), (1, "15.1", {1: 7}), (1, "15.10", {1: 9})])
    assert len(check_rule(rep2, Rule(1, "1", "22", ">0R:15.0:15.1:15.10:", 1, 1))) == 1


def test_column_rule_with_subtraction():
    # =1C:4:1:2:3:  ->  4-ustun = 1 + 2 − 3
    rep = make_report([("2", "1", {1: 10, 2: 5, 3: 3, 4: 12}), ("2", "2", {1: 1, 2: 1, 3: 0, 4: 3})])
    f = check_rule(rep, Rule(1, "2", "1", "=1C:4:1:2:3:"))
    assert [x.where for x in f] == ["2-satr"] and f[0].left == 3 and f[0].right == 2


def test_greater_or_equal_and_missing_section():
    rep = make_report([("3", "1", {1: 5, 2: 6})])
    assert len(check_rule(rep, Rule(1, "3", "1", ">0C:1:2:"))) == 1
    f = check_rule(rep, Rule(1, "9", "1", ">0C:1:2:"))
    assert f and f[0].level == "Nazorat xatosi"


def test_numeric_row_code_cells_match_text_codes():
    rep = make_report([("1", 1, {1: 3}), ("1", 2, {1: 1}), ("1", 3, {1: 2})])
    assert check_rule(rep, Rule(1, "1", "1", "=0R:1:2:3:", 1, 1)) == []


def test_zero_rule_and_bad_shifr():
    rep = make_report([("3", "237", {13: 0}), ("3", "238", {13: -1})])
    f = check_rule(rep, Rule(1, "3", "9", ">0N:237:238:", 13, 13))
    assert len(f) == 1 and "238" in f[0].message
    assert check_rule(rep, Rule(1, "3", "9", "=10C:8:2:9:"))[0].level == "Nazorat xatosi"


def test_completeness_expression():
    rep = make_report([("1.0", "26.0", {1: 4, 3: 0})])
    assert check_completeness(rep, 'D("1.0","26.0",1) > 0 and D("1.0","26.0",3) > 0') is False
    assert check_completeness(rep, 'D("1.0","26.0",1) > 0 or D("1.0","26.0",3) > 0') is True
    assert check_completeness(rep, "") is None

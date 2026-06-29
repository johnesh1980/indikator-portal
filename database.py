import sqlite3
import hashlib
from datetime import datetime

DB_PATH = "indikator.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # Foydalanuvchilar (faqat admin + 14 viloyat)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viloyat',
            viloyat_code TEXT,
            full_name TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Har bir tuman+oy uchun ko'rsatkich qiymatlari
    c.execute("""
        CREATE TABLE IF NOT EXISTS indicator_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            viloyat_code TEXT NOT NULL,
            viloyat_name TEXT NOT NULL,
            tuman_code TEXT NOT NULL,
            tuman_name TEXT NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            quarter TEXT NOT NULL,
            indicator_id INTEGER NOT NULL,
            indicator_name TEXT NOT NULL,
            period TEXT NOT NULL,
            value TEXT DEFAULT '',
            submitted_by TEXT NOT NULL,
            submitted_at TEXT DEFAULT (datetime('now')),
            UNIQUE(tuman_code, year, month, indicator_id)
        )
    """)

    # Viloyat jami (qo'lda kiritilgan + tekshirilgan)
    c.execute("""
        CREATE TABLE IF NOT EXISTS viloyat_jami (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_number TEXT NOT NULL,
            viloyat_code TEXT NOT NULL,
            viloyat_name TEXT NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            quarter TEXT NOT NULL,
            indicator_id INTEGER NOT NULL,
            indicator_name TEXT NOT NULL,
            viloyat_value TEXT DEFAULT '',
            tuman_sum REAL,
            is_locked INTEGER DEFAULT 1,
            submitted_by TEXT NOT NULL,
            submitted_at TEXT DEFAULT (datetime('now')),
            UNIQUE(viloyat_code, year, month, indicator_id)
        )
    """)

    # Admin
    admin_hash = hash_password("Admin@2030")
    c.execute("""
        INSERT OR IGNORE INTO users (username, password_hash, role, full_name)
        VALUES ('admin', ?, 'admin', 'Тизим администратори')
    """, (admin_hash,))

    # 14 viloyat foydalanuvchisi
    from data import VILOYAT_USERS, REGIONS
    for username, vcode in VILOYAT_USERS.items():
        vname = REGIONS[vcode]["name"]
        default_pass = username.capitalize() + "@2030"
        phash = hash_password(default_pass)
        c.execute("""
            INSERT OR IGNORE INTO users
            (username, password_hash, role, viloyat_code, full_name)
            VALUES (?, ?, 'viloyat', ?, ?)
        """, (username, phash, vcode, vname))

    conn.commit()
    conn.close()

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def verify_user(username, password):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM users
        WHERE username=? AND password_hash=? AND is_active=1
    """, (username, hash_password(password)))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

# ── TUMANLAR MA'LUMOTLARI ────────────────────────────────────────────────────

def save_tuman_data(viloyat_code, viloyat_name, tuman_code, tuman_name,
                    year, month, quarter, submitted_by, values_dict, indicators):
    """Bitta tumannig ko'rsatkichlarini saqlash (yoki yangilash)"""
    conn = get_conn()
    c = conn.cursor()
    for ind in indicators:
        val = values_dict.get(str(ind["id"]), "")
        c.execute("""
            INSERT INTO indicator_data
            (viloyat_code, viloyat_name, tuman_code, tuman_name,
             year, month, quarter, indicator_id, indicator_name, period,
             value, submitted_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(tuman_code, year, month, indicator_id)
            DO UPDATE SET value=excluded.value,
                          submitted_by=excluded.submitted_by,
                          submitted_at=datetime('now')
        """, (viloyat_code, viloyat_name, tuman_code, tuman_name,
              year, month, quarter, ind["id"], ind["name"], ind["period"],
              val, submitted_by))
    conn.commit()
    conn.close()

def is_tuman_submitted(tuman_code, year, month):
    """Tuman uchun ma'lumot bormi?"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) as cnt FROM indicator_data
        WHERE tuman_code=? AND year=? AND month=? AND value != ''
    """, (tuman_code, year, month))
    row = c.fetchone()
    conn.close()
    return row["cnt"] > 0

def get_tuman_values(tuman_code, year, month):
    """Tumanning mavjud qiymatlarini olish"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT indicator_id, value FROM indicator_data
        WHERE tuman_code=? AND year=? AND month=?
    """, (tuman_code, year, month))
    rows = c.fetchall()
    conn.close()
    return {str(r["indicator_id"]): r["value"] for r in rows}

def get_submitted_tumans(viloyat_code, year, month):
    """Viloyatda ma'lumot kiritilgan tumanlar"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT tuman_code FROM indicator_data
        WHERE viloyat_code=? AND year=? AND month=? AND value != ''
    """, (viloyat_code, year, month))
    rows = c.fetchall()
    conn.close()
    return set(r["tuman_code"] for r in rows)

def compute_tuman_sums(viloyat_code, year, month):
    """Har bir ko'rsatkich uchun tumanlar yig'indisi"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT indicator_id, tuman_name, value FROM indicator_data
        WHERE viloyat_code=? AND year=? AND month=? AND value != ''
        ORDER BY indicator_id, tuman_name
    """, (viloyat_code, year, month))
    rows = c.fetchall()
    conn.close()

    sums = {}    # ind_id -> float
    details = {} # ind_id -> {tuman_name: value_str}
    for row in rows:
        ind_id = row["indicator_id"]
        tname  = row["tuman_name"]
        val_s  = (row["value"] or "").strip()
        if ind_id not in details:
            details[ind_id] = {}
        details[ind_id][tname] = val_s
        try:
            num = float(val_s.replace(",", ".").replace(" ", "").replace("%", ""))
            sums[ind_id] = sums.get(ind_id, 0.0) + num
        except (ValueError, AttributeError):
            pass
    return sums, details

# ── VILOYAT JAMI ─────────────────────────────────────────────────────────────

def is_viloyat_jami_locked(viloyat_code, year, month):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) as cnt FROM viloyat_jami
        WHERE viloyat_code=? AND year=? AND month=? AND is_locked=1
    """, (viloyat_code, year, month))
    row = c.fetchone()
    conn.close()
    return row["cnt"] > 0

def save_viloyat_jami(viloyat_code, viloyat_name, year, month, quarter,
                      submitted_by, values_dict, tuman_sums, indicators):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now()
    ref = f"SSV-V-{viloyat_code}-{year}{month:02d}-{now.strftime('%H%M%S')}"
    for ind in indicators:
        ind_id = ind["id"]
        val = values_dict.get(str(ind_id), "")
        tsum = tuman_sums.get(ind_id)
        c.execute("""
            INSERT INTO viloyat_jami
            (ref_number, viloyat_code, viloyat_name, year, month, quarter,
             indicator_id, indicator_name, viloyat_value, tuman_sum,
             submitted_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(viloyat_code, year, month, indicator_id)
            DO UPDATE SET viloyat_value=excluded.viloyat_value,
                          tuman_sum=excluded.tuman_sum,
                          submitted_by=excluded.submitted_by,
                          submitted_at=datetime('now'),
                          is_locked=1
        """, (ref, viloyat_code, viloyat_name, year, month, quarter,
              ind_id, ind["name"], val, tsum, submitted_by))
    conn.commit()
    conn.close()
    return ref

def get_viloyat_jami_values(viloyat_code, year, month):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT indicator_id, viloyat_value, tuman_sum FROM viloyat_jami
        WHERE viloyat_code=? AND year=? AND month=?
    """, (viloyat_code, year, month))
    rows = c.fetchall()
    conn.close()
    return {str(r["indicator_id"]): r["viloyat_value"] for r in rows}

# ── ADMIN: BARCHA MA'LUMOTLAR ─────────────────────────────────────────────────

def get_all_tuman_data(viloyat_code=None, year=None, month=None):
    conn = get_conn()
    c = conn.cursor()
    q = "SELECT * FROM indicator_data WHERE 1=1"
    p = []
    if viloyat_code: q += " AND viloyat_code=?"; p.append(viloyat_code)
    if year:         q += " AND year=?";          p.append(year)
    if month:        q += " AND month=?";          p.append(month)
    q += " ORDER BY viloyat_code, tuman_code, indicator_id"
    c.execute(q, p)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_users():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id,username,role,viloyat_code,full_name,is_active FROM users ORDER BY role,username")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def change_password(username, new_password):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET password_hash=? WHERE username=?",
              (hash_password(new_password), username))
    conn.commit()
    conn.close()

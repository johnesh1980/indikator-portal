import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
import database as db
import data as d

st.set_page_config(
    page_title="Саломатлик 2030 — Кўрсаткичлар портали",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"]{background:#f2f5fb;}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#1a4f8a,#0d3566);}
[data-testid="stSidebar"] *{color:#fff!important;}
.stButton>button{border-radius:8px;font-weight:600;}
.val-ok{color:#15803d;font-weight:700;}
.val-err{color:#dc2626;font-weight:700;}
div[data-testid="stForm"]{background:#fff;border-radius:12px;
  padding:20px;border:1px solid #d0daea;}
</style>
""", unsafe_allow_html=True)

if "user" not in st.session_state:
    st.session_state.user = None

db.init_db()

MONTHS_LIST = list(d.MONTHS_UZ.values())

def to_excel_bytes(df):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Ma'lumotlar")
    return buf.getvalue()

def num_safe(s):
    """Matnni floatga aylantirish, imkon bo'lmasa None"""
    try:
        return float(str(s).replace(",",".").replace(" ","").replace("%","").strip())
    except:
        return None

# ── LOGIN ─────────────────────────────────────────────────────────────────────
def show_login():
    c1,c2,c3 = st.columns([1,1.3,1])
    with c2:
        st.markdown("""
        <div style="text-align:center;padding:30px 0 10px">
          <div style="font-size:56px">🏥</div>
          <h2 style="color:#1a4f8a;margin:8px 0 4px">Саломатлик 2030</h2>
          <p style="color:#6b7a99;font-size:.88rem">
            Кўрсаткичлар онлайн тўлдириш портали<br>
            Ўзбекистон Республикаси СВ
          </p>
        </div>""", unsafe_allow_html=True)
        with st.form("lf"):
            username = st.text_input("Логин", placeholder="andijan / admin")
            password = st.text_input("Парол", type="password")
            if st.form_submit_button("🔐 Кириш", use_container_width=True, type="primary"):
                user = db.verify_user(username.strip(), password.strip())
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Логин ёки парол нотўғри!")
        st.caption("Логин/парол олиш — институт маъмурига мурожаат қилинг")

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
def show_sidebar():
    user = st.session_state.user
    with st.sidebar:
        st.markdown(f"""
        <div style="padding:10px 0 18px;text-align:center">
          <div style="font-size:32px">🏥</div>
          <div style="font-weight:700;font-size:.95rem;margin-top:4px">Саломатлик 2030</div>
          <div style="font-size:.74rem;opacity:.75">Кўрсаткичлар портали</div>
        </div>
        <div style="background:rgba(255,255,255,.12);border-radius:8px;
             padding:10px 12px;margin-bottom:14px">
          <div style="font-size:.73rem;opacity:.7">Кирган фойдаланувчи</div>
          <div style="font-weight:600;font-size:.88rem;margin-top:2px">
            👤 {user['full_name']}</div>
          <div style="font-size:.73rem;opacity:.7;margin-top:1px">
            {'🔑 Администратор' if user['role']=='admin' else '📍 Вилоят вакили'}
          </div>
        </div>""", unsafe_allow_html=True)

        if user["role"] == "admin":
            pages = ["📊 Барча маълумотлар", "📋 Вилоят кесими", "👥 Фойдаланувчилар"]
        else:
            pages = ["📝 Туман кўрсаткичлари", "🏛️ Вилоят жами (текшириш)",
                     "📊 Менинг маълумотларим", "🔑 Паролни ўзгартириш"]

        page = st.radio("", pages, label_visibility="collapsed")
        st.markdown("<hr style='border-color:rgba(255,255,255,.2);margin:14px 0'>",
                    unsafe_allow_html=True)
        if st.button("🚪 Чиқиш", use_container_width=True):
            st.session_state.user = None
            st.rerun()
    return page

# ── DAVR TANLASH (umumiy widget) ──────────────────────────────────────────────
def period_selector(key=""):
    c1,c2,c3 = st.columns(3)
    with c1:
        year = st.selectbox("Йил", [2025,2026,2027,2028,2029,2030], index=1, key=f"yr{key}")
    with c2:
        mn = st.selectbox("Ой", MONTHS_LIST, index=5, key=f"mn{key}")
        month = list(d.MONTHS_UZ.keys())[MONTHS_LIST.index(mn)]
    with c3:
        quarter = st.selectbox("Чорак", ["Q1","Q2","Q3","Q4"], index=1, key=f"qr{key}")
    return year, month, mn, quarter

# ══════════════════════════════════════════════════════════════════════════════
# VILOYAT — TUMAN KO'RSATKICHLARI TO'LDIRISH
# ══════════════════════════════════════════════════════════════════════════════
def page_filling():
    user = st.session_state.user
    vcode = user["viloyat_code"]
    region = d.REGIONS[vcode]
    districts = region["districts"]

    st.markdown(f"## 📝 Туман кўрсаткичларини тўлдириш")
    st.markdown(f"**{region['name']}** · {len(districts)} та туман/шаҳар")
    st.info("Ҳар бир туман учун кўрсаткичларни киритинг. Сақланган маълумотлар вилоят жамини"
            " текширишда автоматик йиғилади.")

    year, month, month_name, quarter = period_selector("f")
    pf = st.selectbox("Даврийлик фильтри",
         ["Барчаси","ойлик","чораклик","ярим йиллик","йиллик","бир марталик"], key="pff")
    inds = [i for i in d.INDICATORS if pf=="Барчаси" or i["period"]==pf]

    submitted_set = db.get_submitted_tumans(vcode, year, month)
    c1,c2,c3 = st.columns(3)
    c1.metric("Жами туман", len(districts))
    c2.metric("✅ Маълумот бор", len(submitted_set))
    c3.metric("📝 Бўш", len(districts)-len(submitted_set))

    st.info("📝 Жадвалдаги катакларга бевосита қийматларни киритинг, сўнг «💾 Сақлаш» тугмасини босинг.")

    # Jadval: Tuman (chap, muzlatilgan) + har bir ko'rsatkich (ustun)
    rows = []
    for dist in districts:
        tcode = dist["code"]
        tname = dist["name"]
        existing = db.get_tuman_values(tcode, year, month)
        has_data = tcode in submitted_set
        row = {
            "": "✅" if has_data else "⬜",
            "Туман / Шаҳар": tname,
            "SOATO": tcode,
        }
        for ind in inds:
            col_key = f"{ind['id']}. {ind['name'][:30]} [{ind['period']}]"
            row[col_key] = existing.get(str(ind["id"]), "")
        rows.append(row)

    df_input = pd.DataFrame(rows)

    # Ustun konfiguratsiyasi
    col_config = {
        "": st.column_config.TextColumn("", width=40, disabled=True),
        "Туман / Шаҳар": st.column_config.TextColumn("Туман / Шаҳар", width=170, disabled=True),
        "SOATO": st.column_config.TextColumn("SOATO", width=80, disabled=True),
    }
    for ind in inds:
        col_key = f"{ind['id']}. {ind['name'][:30]} [{ind['period']}]"
        col_config[col_key] = st.column_config.TextColumn(
            f"{ind['id']}. {ind['name'][:28]}",
            help=f"{ind['name']}\nДаврийлик: {ind['period']}\nБазавий: {ind['base']}\nМақсад: {ind['target']}",
            width=110
        )

    edited_df = st.data_editor(
        df_input,
        column_config=col_config,
        hide_index=True,
        use_container_width=True,
        key=f"de_{vcode}_{year}_{month}_{pf}",
        num_rows="fixed",
    )

    c_btn1, c_btn2 = st.columns([1, 5])
    with c_btn1:
        save_clicked = st.button("💾 Сақлаш", type="primary", use_container_width=True)

    if save_clicked:
        saved_count = 0
        for i, dist in enumerate(districts):
            tcode = dist["code"]
            tname = dist["name"]
            row_data = edited_df.iloc[i]
            values = {}
            for ind in inds:
                col_key = f"{ind['id']}. {ind['name'][:30]} [{ind['period']}]"
                values[str(ind["id"])] = str(row_data.get(col_key, "") or "").strip()
            if any(v for v in values.values()):
                db.save_tuman_data(
                    vcode, region["name"], tcode, tname,
                    year, month, quarter,
                    user["username"], values, d.INDICATORS
                )
                saved_count += 1
        st.success(f"✅ {saved_count} та туман маълумотлари сақланди!")
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# VILOYAT JAMI — MANTIQIY NAZORAT
# ══════════════════════════════════════════════════════════════════════════════
def page_viloyat_jami():
    user = st.session_state.user
    vcode = user["viloyat_code"]
    region = d.REGIONS[vcode]
    districts = region["districts"]

    st.markdown("## 🏛️ Вилоят жами кўрсаткичлари")
    st.markdown(f"**{region['name']}** — вилоят жами туманлар йиғиндисига тенглиги текширилади")

    year, month, month_name, quarter = period_selector("vj")

    # Tumanlar holati
    submitted_set = db.get_submitted_tumans(vcode, year, month)
    not_filled = [dd["name"] for dd in districts if dd["code"] not in submitted_set]
    c1,c2,c3 = st.columns(3)
    c1.metric("Жами туман", len(districts))
    c2.metric("✅ Маълумот бор", len(submitted_set))
    c3.metric("⚪ Бўш", len(not_filled))

    if not_filled:
        with st.expander(f"⚪ Маълумот киритилмаган {len(not_filled)} та туман"):
            for n in not_filled: st.markdown(f"• {n}")

    st.markdown("---")

    # Tumanlar yig'indisi
    tuman_sums, tuman_details = db.compute_tuman_sums(vcode, year, month)

    if not tuman_sums:
        st.warning("Ҳали ҳеч бир туман маълумоти йўқ. Аввал «Туман кўрсаткичлари» бўлимини тўлдиринг.")
        return

    # Qulflanganmi?
    locked = db.is_viloyat_jami_locked(vcode, year, month)
    existing_jami = db.get_viloyat_jami_values(vcode, year, month)

    if locked:
        st.success(f"✅ {region['name']} учун {year} й. {month_name} вилоят жами жўнатилган ва қулфланган.")
        st.markdown("### Жўнатилган вилоят жами:")
        rows = []
        for ind in d.INDICATORS:
            ind_id = ind["id"]
            vj_val = existing_jami.get(str(ind_id), "")
            tsum = tuman_sums.get(ind_id)
            tsum_s = f"{tsum:,.2f}".rstrip("0").rstrip(".") if tsum is not None else "—"
            rows.append({
                "#": ind_id,
                "Кўрсаткич": ind["name"][:60],
                "Туманлар йиғ.": tsum_s,
                "Вилоят жами": vj_val,
                "Мос": "✅" if vj_val == tsum_s or _nums_match(vj_val, tsum) else "❌"
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        return

    pf = st.selectbox("Даврийлик фильтри",
         ["Барчаси","ойлик","чораклик","ярим йиллик","йиллик","бир марталик"], key="vjpf")
    inds = [i for i in d.INDICATORS if pf=="Барчаси" or i["period"]==pf]

    st.markdown("### Вилоят жами қийматларини киритинг")
    st.markdown(
        "**Туманлар йиғ.** устуни — тизим туман маълумотларидан автоматик ҳисоблаган. "
        "**Вилоят жами** устунига ўзингиз киритасиз. Жўнатишда мослик текширилади.")

    viloyat_vals = {}
    errors = []

    # Header
    hc1,hc2,hc3,hc4 = st.columns([3.5,1.5,1.5,0.8])
    hc1.markdown("**Кўрсаткич**")
    hc2.markdown("**Туманлар йиғ.**")
    hc3.markdown("**Вилоят жами**")
    hc4.markdown("**Мос?**")
    st.markdown("<hr style='margin:4px 0 8px'>", unsafe_allow_html=True)

    for ind in inds:
        ind_id = ind["id"]
        tsum = tuman_sums.get(ind_id)
        tsum_s = f"{tsum:,.4f}".rstrip("0").rstrip(".") if tsum is not None else "—"
        existing_v = existing_jami.get(str(ind_id), "")

        rc1,rc2,rc3,rc4 = st.columns([3.5,1.5,1.5,0.8])
        with rc1:
            st.markdown(f"<small style='color:#6b7a99'>{ind_id}.</small> {ind['name'][:65]}"
                        f"<br><small style='color:#888'>{ind['period']}</small>",
                        unsafe_allow_html=True)
        with rc2:
            if tsum is not None:
                st.markdown(f"<div style='padding:8px 0;font-weight:700;color:#1a4f8a'>{tsum_s}</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown("<div style='padding:8px 0;color:#aaa'>—</div>", unsafe_allow_html=True)
        with rc3:
            val = st.text_input("", value=existing_v,
                key=f"vj_{ind_id}_{year}_{month}",
                label_visibility="collapsed",
                placeholder=tsum_s)
            viloyat_vals[str(ind_id)] = val
        with rc4:
            if val.strip() and tsum is not None:
                vnum = num_safe(val)
                if vnum is not None and abs(vnum - tsum) < 0.01:
                    st.markdown("✅")
                else:
                    diff = (vnum - tsum) if vnum is not None else None
                    diff_s = f"{diff:+,.2f}" if diff is not None else "?"
                    st.markdown(f"❌")
                    errors.append({
                        "Кўрсаткич": ind["name"][:55],
                        "Вилоят жами": val,
                        "Туманлар йиғ.": tsum_s,
                        "Фарқ": diff_s
                    })
            elif not val.strip():
                st.markdown("⬜")
            else:
                st.markdown("⬜")

        st.markdown("<div style='border-bottom:1px solid #edf2fa;margin:2px 0'></div>",
                    unsafe_allow_html=True)

    # Natija
    st.markdown("---")
    filled_count = sum(1 for v in viloyat_vals.values() if v.strip())
    match_count  = filled_count - len(errors)

    c1,c2,c3 = st.columns(3)
    c1.metric("Киритилган", filled_count)
    c2.metric("✅ Мос", match_count)
    c3.metric("❌ Фарқ бор", len(errors))

    if errors:
        st.error(f"🔒 **{len(errors)} та кўрсаткич туманлар йиғиндисига мос эмас** — "
                 f"жўнатиш блокланди. Қийматларни тўғрилаб қайта уриниб кўринг.")
        st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)
        st.button("🚀 Жўнатиш", disabled=True, type="primary",
                  help="Барча мос бўлгандагина жўнатиш мумкин")
    elif filled_count == 0:
        st.warning("Камида битта қийматни киритинг.")
    else:
        st.success(f"✅ Барча {match_count} та киритилган кўрсаткич туманлар йиғиндисига мос!")
        if st.button("🚀 Вилоят жамини жўнатиш ва қуллаш", type="primary"):
            ref = db.save_viloyat_jami(
                vcode, region["name"], year, month, quarter,
                user["username"], viloyat_vals, tuman_sums, d.INDICATORS
            )
            st.success(f"✅ Жўнатилди! Рақами: **{ref}**")
            st.balloons()
            st.rerun()

def _nums_match(a, b):
    na, nb = num_safe(a), num_safe(b)
    if na is None or nb is None: return False
    return abs(na - nb) < 0.01

# ══════════════════════════════════════════════════════════════════════════════
# VILOYAT — O'Z MA'LUMOTLARI
# ══════════════════════════════════════════════════════════════════════════════
def page_my_data():
    user = st.session_state.user
    vcode = user["viloyat_code"]
    region = d.REGIONS[vcode]

    st.markdown(f"## 📊 {region['name']} — Маълумотлар")
    year, month, month_name, _ = period_selector("md")

    rows_all = db.get_all_tuman_data(vcode, year, month)
    if not rows_all:
        st.info("Танланган давр учун маълумотлар йўқ.")
        return

    # Pivot: tuman x indicator
    pivot = {}
    ind_names = {}
    for r in rows_all:
        tc = r["tuman_code"]
        tn = r["tuman_name"]
        if tc not in pivot:
            pivot[tc] = {"Туман": tn, "SOATO": tc}
        ind_names[r["indicator_id"]] = r["indicator_name"][:40]
        pivot[tc][f"{r['indicator_id']}. {r['indicator_name'][:35]}"] = r["value"]

    df = pd.DataFrame(list(pivot.values()))
    st.dataframe(df, use_container_width=True, hide_index=True)

    if st.button("⬇️ Excel юклаш"):
        st.download_button("📥 Юклаб олиш", to_excel_bytes(df),
            file_name=f"SSV_{vcode}_{year}_{month:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── PAROL O'ZGARTIRISH ────────────────────────────────────────────────────────
def page_change_password():
    user = st.session_state.user
    st.markdown("## 🔑 Паролни ўзгартириш")
    c1,c2,c3 = st.columns([1,1.5,1])
    with c2:
        with st.form("cpf"):
            old = st.text_input("Эски парол", type="password")
            new = st.text_input("Янги парол", type="password")
            new2= st.text_input("Янги паролни такрорланг", type="password")
            if st.form_submit_button("Сақлаш", type="primary", use_container_width=True):
                if not db.verify_user(user["username"], old):
                    st.error("Эски парол нотўғри!")
                elif len(new) < 6:
                    st.error("Парол камида 6 та белги бўлсин!")
                elif new != new2:
                    st.error("Паролlar мос эмас!")
                else:
                    db.change_password(user["username"], new)
                    st.success("✅ Парол ўзгартирилди!")

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN SAHIFALARI
# ══════════════════════════════════════════════════════════════════════════════
def page_admin_all():
    st.markdown("## 📊 Барча маълумотлар")
    c1,c2,c3 = st.columns(3)
    with c1:
        year = st.selectbox("Йил",[2025,2026,2027,2028,2029,2030],index=1,key="aa_yr")
    with c2:
        mn = st.selectbox("Ой", MONTHS_LIST, index=5, key="aa_mn")
        month = list(d.MONTHS_UZ.keys())[MONTHS_LIST.index(mn)]
    with c3:
        vnames = ["Барча вилоятлар"] + [v["name"] for v in d.REGIONS.values()]
        vsel = st.selectbox("Вилоят", vnames, key="aa_v")
        vcode_f = None
        if vsel != "Барча вилоятлар":
            for k,v in d.REGIONS.items():
                if v["name"] == vsel: vcode_f=k; break

    rows_all = db.get_all_tuman_data(vcode_f, year, month)

    total_d = sum(len(v["districts"]) for v in d.REGIONS.values()) if not vcode_f \
              else len(d.REGIONS[vcode_f]["districts"])
    submitted_d = len(set(r["tuman_code"] for r in rows_all))

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Жами туман", total_d)
    c2.metric("Маълумот бор", submitted_d)
    c3.metric("Бўш", total_d - submitted_d)
    c4.metric("Қамров", f"{submitted_d/total_d*100:.1f}%" if total_d else "0%")

    if not rows_all:
        st.info("Маълумотлар йўқ."); return

    # Pivot
    pivot = {}
    for r in rows_all:
        key = (r["tuman_code"], r["year"], r["month"])
        if key not in pivot:
            pivot[key] = {
                "Вилоят": r["viloyat_name"],
                "Туман": r["tuman_name"],
                "SOATO": r["tuman_code"],
                "Йил": r["year"],
                "Ой": d.MONTHS_UZ.get(r["month"], r["month"]),
            }
        pivot[key][f"{r['indicator_id']}"] = r["value"]

    df = pd.DataFrame(list(pivot.values()))
    st.dataframe(df, use_container_width=True, hide_index=True)

    if st.button("⬇️ Excel юклаш (тўлиқ)", type="primary"):
        st.download_button("📥 Юклаб олиш", to_excel_bytes(df),
            file_name=f"SSV_Barcha_{year}_{month:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def page_admin_viloyat():
    st.markdown("## 📋 Вилоят кесимида қамров")
    c1,c2 = st.columns(2)
    with c1:
        year = st.selectbox("Йил",[2025,2026,2027,2028,2029,2030],index=1,key="av_yr")
    with c2:
        mn = st.selectbox("Ой", MONTHS_LIST, index=5, key="av_mn")
        month = list(d.MONTHS_UZ.keys())[MONTHS_LIST.index(mn)]

    rows=[]
    for vcode, region in d.REGIONS.items():
        submitted = db.get_submitted_tumans(vcode, year, month)
        total = len(region["districts"])
        done  = len(submitted)
        pct   = done/total*100 if total else 0
        jami  = "✅ Жўнатилган" if db.is_viloyat_jami_locked(vcode, year, month) else "⏳ Кутилмоқда"
        rows.append({
            "Вилоят": region["name"],
            "Жами туман": total,
            "Маълумот бор": done,
            "Бўш": total-done,
            "Қамров %": f"{pct:.1f}%",
            "Вилоят жами": jami,
            "Ҳолат": "✅ Тўлиқ" if done==total else ("⚠️ Қисман" if done>0 else "❌ Йўқ"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

def page_admin_users():
    st.markdown("## 👥 Фойдаланувчилар")
    users = db.get_all_users()
    rows = []
    for u in users:
        vn = d.REGIONS.get(u["viloyat_code"],{}).get("name","—") if u["viloyat_code"] else "—"
        rows.append({
            "Логин": u["username"],
            "Роль": "🔑 Админ" if u["role"]=="admin" else "📍 Вилоят",
            "Вилоят": vn,
            "Тўлиқ исм": u["full_name"],
            "Ҳолат": "✅" if u["is_active"] else "❌",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### Default логин / парол жадвали")
    lrows=[]
    for uname, vcode in d.VILOYAT_USERS.items():
        lrows.append({"Логин": uname,
                      "Default парол": uname.capitalize()+"@2030",
                      "Вилоят": d.REGIONS[vcode]["name"]})
    st.dataframe(pd.DataFrame(lrows), use_container_width=True, hide_index=True)
    st.warning("⚠️ Default parollarni viloyat xodimlari birinchi kirishda o'zgartirsin!")

    st.markdown("---")
    st.markdown("#### 🔑 Паролни алмаштириш")
    non_admins = [u["username"] for u in users if u["role"]!="admin"]
    c1,c2,c3 = st.columns(3)
    with c1: sel = st.selectbox("Фойдаланувчи", non_admins)
    with c2: np  = st.text_input("Янги парол", type="password")
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("💾 Сақлаш"):
            if len(np)<6: st.error("Камида 6 та белги!")
            else:
                db.change_password(sel, np)
                st.success(f"✅ {sel} парoli ўзгартирилди!")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    if not st.session_state.user:
        show_login(); return
    page = show_sidebar()
    user = st.session_state.user
    if user["role"] == "admin":
        if   page == "📊 Барча маълумотлар": page_admin_all()
        elif page == "📋 Вилоят кесими":     page_admin_viloyat()
        elif page == "👥 Фойдаланувчилар":   page_admin_users()
    else:
        if   page == "📝 Туман кўрсаткичлари":        page_filling()
        elif page == "🏛️ Вилоят жами (текшириш)":    page_viloyat_jami()
        elif page == "📊 Менинг маълумотларим":        page_my_data()
        elif page == "🔑 Паролни ўзгартириш":          page_change_password()

if __name__ == "__main__":
    main()

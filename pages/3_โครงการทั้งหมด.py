"""หน้ารายการโครงการทั้งหมด + รายละเอียดโครงการ (TOR / ความเสี่ยง / โอกาสชนะงาน / เนื้อหาขาย)"""

import streamlit as st
import db
import ai_engine
import auth

current = auth.require_role(["admin", "sales", "procurement", "legal"])
auth.sidebar_user_info()
can_edit = current["role"] in ("admin", "sales")
if not can_edit:
    st.info("🔎 คุณมีสิทธิ์ดูข้อมูลอย่างเดียว (read-only) — เฉพาะฝ่ายขายและผู้ดูแลระบบที่แก้ไข/สั่งวิเคราะห์ได้ในหน้านี้")

STATUS_OPTIONS = {
    "analyzing": "🔵 กำลังวิเคราะห์",
    "ready": "🟢 พร้อมยื่นข้อเสนอ",
    "submitted": "🟡 ยื่นข้อเสนอแล้ว รอผล",
    "won": "🏆 ชนะงาน",
    "lost": "⚪ ไม่ได้งาน",
    "contract_active": "📋 อยู่ระหว่างดำเนินสัญญา",
    "contract_completed": "✅ ปิดสัญญาแล้ว",
}

st.title("📁 โครงการทั้งหมด")

projects = db.list_projects()
if not projects:
    st.info("ยังไม่มีโครงการ — ไปที่หน้า วิเคราะห์ TOR ใหม่ เพื่อเริ่มต้น")
    st.stop()

# ---------------- รายการ (sidebar-like selector) ----------------
project_map = {f"{p['name']}  —  {STATUS_OPTIONS.get(p['status'], p['status'])}": p["id"] for p in projects}
default_id = st.session_state.get("selected_project_id", projects[0]["id"])
default_label = next((k for k, v in project_map.items() if v == default_id), list(project_map.keys())[0])

selected_label = st.selectbox("เลือกโครงการ", list(project_map.keys()), index=list(project_map.keys()).index(default_label))
project_id = project_map[selected_label]
st.session_state["selected_project_id"] = project_id

project = db.get_project(project_id)

# ---------------- แถบควบคุมสถานะ / ลบ ----------------
c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    new_status = st.selectbox(
        "สถานะโครงการ", list(STATUS_OPTIONS.keys()),
        format_func=lambda k: STATUS_OPTIONS[k],
        index=list(STATUS_OPTIONS.keys()).index(project["status"]) if project["status"] in STATUS_OPTIONS else 0,
        disabled=not can_edit,
    )
    if can_edit and new_status != project["status"]:
        db.update_project(project_id, status=new_status)
        db.log_audit(current["id"], current["email"], "change_status", "project", project_id, new_status)
        st.rerun()
with c3:
    if st.button("🗑️ ลบโครงการนี้", disabled=not can_edit):
        db.delete_project(project_id)
        db.log_audit(current["id"], current["email"], "delete_project", "project", project_id)
        st.session_state.pop("selected_project_id", None)
        st.rerun()

if project["status"] == "won":
    st.success("โครงการนี้ชนะงานแล้ว — ไปที่หน้า **บริหารสัญญา** เพื่อแตก milestone และติดตามความคืบหน้า")

# ---------------- Bid/No-Bid gate: ตัดสินใจก่อนลงแรงทำ BOM/ขาย ----------------
win = project.get("win_probability")
if not project.get("tor_analysis"):
    st.info("🚦 **ขั้นตอนแรก:** ยังไม่มีผลวิเคราะห์ TOR — ไปที่แท็บ **📄 วิเคราะห์ TOR** ด้านล่างเพื่อวิเคราะห์ก่อน จากนั้นจึงประเมินความเสี่ยงและโอกาสชนะงานเพื่อตัดสินใจ Bid/No-Bid")
elif not win:
    st.warning("🚦 **ยังไม่ได้ตัดสินใจ Bid/No-Bid** — ไปที่แท็บ **⚠️ ความเสี่ยง** แล้วตามด้วย **🎯 โอกาสชนะงาน** เพื่อให้ AI ช่วยตัดสินใจก่อนว่าควรยื่นข้อเสนอโครงการนี้หรือไม่ ก่อนจะลงแรงทำ BOM/เนื้อหาขาย")
else:
    rec = win.get("recommendation", "")
    pct = win.get("win_probability_percent", "-")
    if rec == "ไม่ควรเข้าประมูล":
        st.error(f"🚦 **คำแนะนำ Bid/No-Bid: {rec}** (โอกาสชนะงาน {pct}%) — พิจารณาให้รอบคอบก่อนลงแรงทำ BOM/เนื้อหาขายต่อ ดูเหตุผลในแท็บ 🎯 โอกาสชนะงาน")
    elif rec == "ควรพิจารณาอย่างระมัดระวัง":
        st.warning(f"🚦 **คำแนะนำ Bid/No-Bid: {rec}** (โอกาสชนะงาน {pct}%) — ดูรายละเอียดในแท็บ 🎯 โอกาสชนะงาน ก่อนตัดสินใจลงแรงต่อ")
    else:
        st.success(f"🚦 **คำแนะนำ Bid/No-Bid: {rec}** (โอกาสชนะงาน {pct}%) — พร้อมไปต่อที่ BOM/ต้นทุน และเนื้อหาขาย")

st.divider()

tab_tor, tab_risk, tab_win, tab_sales, tab_bom, tab_competitor = st.tabs(
    ["📄 วิเคราะห์ TOR", "⚠️ ความเสี่ยง", "🎯 โอกาสชนะงาน", "💼 เนื้อหาขาย", "🧮 BOM/ต้นทุน", "🕵️ คู่แข่ง"]
)

company_profile = db.get_company_profile() or {}

# ---------------- Tab: TOR ----------------
with tab_tor:
    tor = project.get("tor_analysis")
    if not tor:
        st.warning("ยังไม่มีผลวิเคราะห์ TOR")
    else:
        c1, c2 = st.columns(2)
        c1.markdown(f"**โครงการ:** {tor.get('project_name', '-')}")
        c1.markdown(f"**หน่วยงาน/ลูกค้า:** {tor.get('agency_or_client', '-')}")
        c1.markdown(f"**งบประมาณ:** {tor.get('budget_estimate_thb', '-')}")
        c2.markdown(f"**กำหนดยื่นข้อเสนอ:** {tor.get('submission_deadline', '-')}")
        c2.markdown(f"**ระยะเวลาโครงการ:** {tor.get('project_duration', '-')}")

        st.markdown("**สรุปขอบเขตงาน**")
        st.write(tor.get("scope_summary", "-"))

        colA, colB = st.columns(2)
        with colA:
            st.markdown("**คุณสมบัติผู้ยื่นข้อเสนอ**")
            for q in tor.get("qualification_requirements", []):
                st.markdown(f"- {q}")
            st.markdown("**เอกสารที่ต้องยื่น**")
            for d in tor.get("mandatory_documents", []):
                st.markdown(f"- {d}")
        with colB:
            st.markdown("**เกณฑ์การให้คะแนน**")
            for e in tor.get("evaluation_criteria", []):
                w = e.get("weight_percent", "")
                st.markdown(f"- {e.get('criterion', '')}" + (f" ({w}%)" if w else ""))
            st.markdown("**ความเสี่ยงจาก TOR**")
            for r in tor.get("key_risks", []):
                st.markdown(f"- {r}")

        if tor.get("penalty_clauses"):
            st.markdown("**เงื่อนไขค่าปรับ/บทลงโทษ**")
            st.write(tor.get("penalty_clauses"))
        if tor.get("notes"):
            st.markdown("**ข้อสังเกตเพิ่มเติม**")
            st.write(tor.get("notes"))

# ---------------- Tab: Risk ----------------
with tab_risk:
    risk = project.get("risk_assessment")
    if not risk:
        if st.button("⚠️ ประเมินความเสี่ยงด้วย AI", disabled=not can_edit):
            with st.spinner("กำลังประเมินความเสี่ยง..."):
                try:
                    risk = ai_engine.assess_risk(project.get("tor_analysis", {}), company_profile)
                    db.update_project(project_id, risk_assessment=risk)
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")
    else:
        st.metric("ระดับความเสี่ยงรวม", f"{risk.get('overall_risk_level', '-')}", f"คะแนน {risk.get('overall_risk_score', '-')}/5")
        cols = st.columns(5)
        dims = [
            ("การเงิน", "financial_risk"), ("เทคนิค", "technical_risk"), ("ระยะเวลา", "timeline_risk"),
            ("การแข่งขัน", "competition_risk"), ("กฎหมาย/ข้อกำหนด", "legal_compliance_risk"),
        ]
        for col, (label, key) in zip(cols, dims):
            d = risk.get(key, {})
            col.metric(label, f"{d.get('score', '-')}/5")
        st.markdown("**คำอธิบายความเสี่ยงรายมิติ**")
        for label, key in dims:
            d = risk.get(key, {})
            if d.get("reason"):
                st.markdown(f"- **{label}:** {d.get('reason')}")
        st.markdown("**สรุปภาพรวมความเสี่ยง**")
        st.write(risk.get("risk_narrative", "-"))
        st.markdown("**ข้อเสนอแนะการบรรเทาความเสี่ยง**")
        for m in risk.get("mitigation_suggestions", []):
            st.markdown(f"- {m}")
        if st.button("🔄 ประเมินความเสี่ยงใหม่", disabled=not can_edit):
            with st.spinner("กำลังประเมินความเสี่ยง..."):
                risk = ai_engine.assess_risk(project.get("tor_analysis", {}), company_profile)
                db.update_project(project_id, risk_assessment=risk)
                st.rerun()

# ---------------- Tab: Win probability ----------------
with tab_win:
    win = project.get("win_probability")
    if not win:
        disabled = not project.get("risk_assessment") or not can_edit
        if not project.get("risk_assessment"):
            st.info("กรุณาประเมินความเสี่ยงก่อน")
        if st.button("🎯 ประเมินโอกาสชนะงานด้วย AI", disabled=disabled):
            with st.spinner("กำลังประเมินโอกาสชนะงาน..."):
                try:
                    win = ai_engine.estimate_win_probability(
                        project.get("tor_analysis", {}), project.get("risk_assessment", {}), company_profile
                    )
                    db.update_project(project_id, win_probability=win)
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")
    else:
        st.metric("โอกาสชนะงาน", f"{win.get('win_probability_percent', '-')}%")
        st.markdown(f"**คำแนะนำ:** {win.get('recommendation', '-')}")
        colA, colB = st.columns(2)
        with colA:
            st.markdown("**จุดแข็ง**")
            for s in win.get("key_strengths", []):
                st.markdown(f"- {s}")
        with colB:
            st.markdown("**จุดอ่อน**")
            for w in win.get("key_weaknesses", []):
                st.markdown(f"- {w}")
        if win.get("competitive_positioning"):
            st.markdown("**การวางตำแหน่งเทียบคู่แข่ง**")
            st.write(win.get("competitive_positioning"))
        st.markdown("**เหตุผลประกอบ**")
        st.write(win.get("reasoning", "-"))
        if st.button("🔄 ประเมินโอกาสชนะงานใหม่", disabled=not can_edit):
            with st.spinner("กำลังประเมินโอกาสชนะงาน..."):
                win = ai_engine.estimate_win_probability(
                    project.get("tor_analysis", {}), project.get("risk_assessment", {}), company_profile
                )
                db.update_project(project_id, win_probability=win)
                st.rerun()

# ---------------- Tab: Sales support ----------------
with tab_sales:
    sales = project.get("sales_support")
    if not sales:
        disabled = not project.get("win_probability") or not can_edit
        if not project.get("win_probability"):
            st.info("กรุณาประเมินโอกาสชนะงานก่อน")
        if st.button("💼 สร้างเนื้อหาสนับสนุนการขายด้วย AI", disabled=disabled):
            with st.spinner("กำลังสร้างเนื้อหาสนับสนุนการขาย..."):
                try:
                    sales = ai_engine.generate_sales_support(
                        project.get("tor_analysis", {}), project.get("win_probability", {}), company_profile
                    )
                    db.update_project(project_id, sales_support=sales)
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")
    else:
        st.markdown("**บทสรุปผู้บริหาร**")
        st.write(sales.get("executive_summary", "-"))
        st.markdown("**Value Proposition**")
        st.write(sales.get("value_proposition", "-"))
        colA, colB = st.columns(2)
        with colA:
            st.markdown("**จุดต่างที่โดดเด่น**")
            for d in sales.get("key_differentiators", []):
                st.markdown(f"- {d}")
        with colB:
            st.markdown("**Key Messages สำหรับทีมขาย**")
            for m in sales.get("key_messages", []):
                st.markdown(f"- {m}")
        if sales.get("objection_handling"):
            st.markdown("**การรับมือข้อโต้แย้งของลูกค้า/กรรมการ**")
            for oh in sales.get("objection_handling", []):
                st.markdown(f"- **ข้อโต้แย้ง:** {oh.get('objection', '')}  \n  **แนวตอบ:** {oh.get('response', '')}")
        if sales.get("pricing_strategy_notes"):
            st.markdown("**ข้อสังเกตด้านกลยุทธ์ราคา**")
            st.write(sales.get("pricing_strategy_notes"))
        if st.button("🔄 สร้างเนื้อหาขายใหม่", disabled=not can_edit):
            with st.spinner("กำลังสร้างเนื้อหาสนับสนุนการขาย..."):
                sales = ai_engine.generate_sales_support(
                    project.get("tor_analysis", {}), project.get("win_probability", {}), company_profile
                )
                db.update_project(project_id, sales_support=sales)
                st.rerun()

# ---------------- Tab: BOM / Costing ----------------
with tab_bom:
    bom = db.get_bom_for_project(project_id)
    if not bom:
        disabled = not project.get("tor_analysis") or not can_edit
        if not project.get("tor_analysis"):
            st.info("กรุณาวิเคราะห์ TOR ก่อน")
        if st.button("🧮 ร่าง Solution Architecture + BOM ด้วย AI", disabled=disabled):
            with st.spinner("กำลังร่างโครงสร้างวิธีแก้ไขปัญหาและคำนวณ BOM..."):
                try:
                    result = ai_engine.generate_bom_costing(project.get("tor_analysis", {}), company_profile)
                    bom_id = db.create_bom(
                        project_id,
                        solution_architecture_summary=result.get("solution_architecture_summary", ""),
                    )
                    db.add_bom_items(bom_id, result.get("items", []))
                    db.recalc_bom_totals(bom_id)
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")
    else:
        st.markdown("**Solution Architecture**")
        st.write(bom.get("solution_architecture_summary", "-"))

        items = db.get_bom_items(bom["id"])
        totals = db.recalc_bom_totals(bom["id"])
        c1, c2, c3 = st.columns(3)
        c1.metric("ต้นทุนรวมประเมิน", f"{totals['total_cost']:,.0f} บาท")
        c2.metric("ราคาขายรวม", f"{totals['total_price']:,.0f} บาท")
        c3.metric("Margin", f"{totals['margin_percent']:.1f}%")

        st.markdown("**รายการ BOM** (แก้ไขราคาต้นทุน/ราคาขายได้โดยตรง)")
        for it in items:
            with st.container(border=True):
                cols = st.columns([2, 2, 1, 1, 1, 1])
                cols[0].markdown(f"**{it['item_name']}**")
                cols[0].caption(f"{it['category']} — {it.get('spec', '')}")
                cols[1].caption(f"{it['qty']} {it['unit']}")
                new_cost = cols[2].number_input("ต้นทุน/หน่วย", value=float(it.get("unit_cost") or 0), key=f"cost_{it['id']}", label_visibility="collapsed", disabled=not can_edit)
                new_price = cols[3].number_input("ราคา/หน่วย", value=float(it.get("unit_price") or 0), key=f"price_{it['id']}", label_visibility="collapsed", disabled=not can_edit)
                if cols[4].button("💾", key=f"save_bom_{it['id']}", disabled=not can_edit):
                    db.update_bom_item(it["id"], unit_cost=new_cost, unit_price=new_price)
                    db.recalc_bom_totals(bom["id"])
                    st.rerun()
                if cols[5].button("🗑️", key=f"del_bom_{it['id']}", disabled=not can_edit):
                    db.delete_bom_item(it["id"])
                    db.recalc_bom_totals(bom["id"])
                    st.rerun()

        if st.button("🔄 ร่าง BOM ใหม่ทั้งหมด (จะแทนที่รายการเดิม)", disabled=not can_edit):
            with st.spinner("กำลังร่าง BOM ใหม่..."):
                result = ai_engine.generate_bom_costing(project.get("tor_analysis", {}), company_profile)
                new_bom_id = db.create_bom(project_id, solution_architecture_summary=result.get("solution_architecture_summary", ""))
                db.add_bom_items(new_bom_id, result.get("items", []))
                db.recalc_bom_totals(new_bom_id)
                st.rerun()

# ---------------- Tab: Competitor Intelligence ----------------
with tab_competitor:
    st.caption(
        "ระบบยังไม่ดึงข้อมูลจาก e-GP หรือแหล่งข้อมูลภายนอกอัตโนมัติ — วางข้อมูลคู่แข่งที่ทราบ "
        "(เช่น จากประสบการณ์ตรง หรือข้อมูลที่ไปสืบค้นจาก e-GP มาเอง) แล้วให้ AI วิเคราะห์จุดข่ม"
    )
    with st.form("add_competitor_form"):
        c1, c2 = st.columns(2)
        competitor_name = c1.text_input("ชื่อคู่แข่ง")
        estimated_bid_price = c2.text_input("ราคาที่คาดว่าจะเสนอ (ถ้าทราบ)")
        past_win_rate = c1.text_input("อัตราชนะงานในอดีต (ถ้าทราบ)")
        source = c2.text_input("แหล่งข้อมูล", placeholder="เช่น e-GP, ประสบการณ์ตรง")
        strengths = st.text_area("จุดแข็งของคู่แข่งที่ทราบ")
        weaknesses = st.text_area("จุดอ่อนของคู่แข่งที่ทราบ")
        add_submitted = st.form_submit_button("➕ เพิ่มคู่แข่งและวิเคราะห์ด้วย AI", disabled=not can_edit)

    if can_edit and add_submitted and competitor_name.strip():
        with st.spinner("กำลังวิเคราะห์คู่แข่ง..."):
            try:
                competitor_info_text = (
                    f"ชื่อ: {competitor_name}\nราคาที่คาดว่าจะเสนอ: {estimated_bid_price}\n"
                    f"อัตราชนะงานในอดีต: {past_win_rate}\nจุดแข็ง: {strengths}\nจุดอ่อน: {weaknesses}"
                )
                analysis = ai_engine.analyze_competitor(project.get("tor_analysis", {}), company_profile, competitor_info_text)
                db.add_competitor(project_id, {
                    "competitor_name": competitor_name, "estimated_bid_price": estimated_bid_price,
                    "past_win_rate": past_win_rate, "strengths": strengths, "weaknesses": weaknesses,
                    "source": source, "ai_differentiator_suggestions": analysis.get("differentiator_suggestions", ""),
                })
                st.rerun()
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาด: {e}")

    competitors = db.get_competitors(project_id)
    for comp in competitors:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{comp['competitor_name']}**")
            c1.caption(f"ราคาที่คาดว่าจะเสนอ: {comp.get('estimated_bid_price', '-')} | อัตราชนะในอดีต: {comp.get('past_win_rate', '-')}")
            if c2.button("🗑️ ลบ", key=f"del_comp_{comp['id']}", disabled=not can_edit):
                db.delete_competitor(comp["id"])
                st.rerun()
            if comp.get("strengths"):
                st.markdown(f"**จุดแข็ง:** {comp['strengths']}")
            if comp.get("weaknesses"):
                st.markdown(f"**จุดอ่อน:** {comp['weaknesses']}")
            if comp.get("ai_differentiator_suggestions"):
                st.markdown(f"**🎯 จุดข่มที่ AI แนะนำ:** {comp['ai_differentiator_suggestions']}")

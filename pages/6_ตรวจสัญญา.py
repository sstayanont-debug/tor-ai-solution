"""หน้าตรวจร่างสัญญา (Contract Redlining) — AI สแกนหาข้อเสี่ยง + ดึงข้อผูกมัด (obligations) ทั้งหมด"""

import io
import streamlit as st
import db
import ai_engine
import auth

auth.require_role(["admin", "legal"])
auth.sidebar_user_info()

st.title("⚖️ ตรวจร่างสัญญา (Contract Redlining)")
st.caption(
    "วางหรืออัปโหลดร่างสัญญาที่ได้รับจากคู่ค้า ให้ AI ช่วยคัดกรองข้อที่เสี่ยง/เสียเปรียบเบื้องต้น "
    "และดึงข้อผูกมัด (obligations) ทั้งหมดออกมาเป็นรายการติดตาม — นี่คือการคัดกรองเบื้องต้นด้วย AI "
    "**ไม่ใช่คำแนะนำทางกฎหมายที่สมบูรณ์** ควรให้ฝ่ายกฎหมายตรวจสอบทุกครั้งก่อนลงนามจริง"
)

BID_STATUSES = {"won", "contract_active", "contract_completed"}
projects = [p for p in db.list_projects() if p["status"] in BID_STATUSES]

if not projects:
    st.info("ยังไม่มีโครงการที่ชนะงาน — เมื่อชนะงานแล้วเปลี่ยนสถานะโครงการเป็น 'ชนะงาน' ก่อน")
    st.stop()

project_map = {p["name"]: p["id"] for p in projects}
selected_name = st.selectbox("เลือกโครงการ", list(project_map.keys()))
project_id = project_map[selected_name]
company_profile = db.get_company_profile() or {}

st.divider()

contracts = db.get_contracts_for_project(project_id)

with st.expander("➕ อัปโหลด/วางร่างสัญญาใหม่", expanded=not contracts):
    tab_paste, tab_upload = st.tabs(["✍️ วางข้อความ", "📎 อัปโหลดไฟล์ (PDF/DOCX/TXT)"])
    contract_text = ""
    with tab_paste:
        pasted = st.text_area("วางเนื้อหาร่างสัญญาที่นี่", height=250)
        if pasted.strip():
            contract_text = pasted
    with tab_upload:
        uploaded = st.file_uploader("เลือกไฟล์สัญญา", type=["pdf", "docx", "txt"])
        if uploaded is not None:
            name = uploaded.name.lower()
            data = uploaded.read()
            try:
                if name.endswith(".pdf"):
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(data))
                    contract_text = "\n".join((p.extract_text() or "") for p in reader.pages)
                elif name.endswith(".docx"):
                    import docx
                    document = docx.Document(io.BytesIO(data))
                    contract_text = "\n".join(p.text for p in document.paragraphs)
                else:
                    contract_text = data.decode("utf-8", errors="ignore")
                st.text_area("ข้อความที่สกัดได้", value=contract_text, height=200, key="contract_preview")
                contract_text = st.session_state.get("contract_preview", contract_text)
            except Exception as e:
                st.error(f"อ่านไฟล์ไม่สำเร็จ: {e}")

    if st.button("⚖️ Redline สัญญาด้วย AI", type="primary", disabled=not contract_text.strip()):
        with st.spinner("กำลังตรวจสัญญา (อาจใช้เวลาสักครู่สำหรับเอกสารยาว)..."):
            try:
                contract_id = db.create_contract(project_id, contract_text)
                redline = ai_engine.redline_contract(contract_text, company_profile)
                db.update_contract_redline(contract_id, redline.get("clauses", []), redline.get("overall_risk_summary", ""))
                st.rerun()
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาด: {e}")

if not contracts:
    st.stop()

st.divider()
contract_map = {f"ฉบับ v{c['version']} — {c['uploaded_at'][:16].replace('T',' ')}": c["id"] for c in contracts}
selected_contract_label = st.selectbox("เลือกฉบับสัญญา", list(contract_map.keys()))
contract_id = contract_map[selected_contract_label]
contract = next(c for c in contracts if c["id"] == contract_id)

tab_redline, tab_obligations = st.tabs(["🚩 ผล Redline", "📌 ข้อผูกมัด (Obligations)"])

RISK_COLOR = {"สูง": "🔴", "ปานกลาง": "🟡", "ต่ำ": "🟢"}

with tab_redline:
    if contract.get("overall_risk_summary"):
        st.markdown("**สรุปภาพรวมความเสี่ยง**")
        st.write(contract["overall_risk_summary"])
    clauses = contract.get("redline_result") or []
    if not clauses:
        st.info("ยังไม่มีผล redline สำหรับฉบับนี้")
    else:
        high = [c for c in clauses if c.get("risk_level") == "สูง"]
        med = [c for c in clauses if c.get("risk_level") == "ปานกลาง"]
        low = [c for c in clauses if c.get("risk_level") == "ต่ำ"]
        c1, c2, c3 = st.columns(3)
        c1.metric("เสี่ยงสูง", len(high))
        c2.metric("เสี่ยงปานกลาง", len(med))
        c3.metric("เสี่ยงต่ำ", len(low))
        for clause in high + med + low:
            icon = RISK_COLOR.get(clause.get("risk_level", ""), "")
            with st.container(border=True):
                st.markdown(f"{icon} **ระดับความเสี่ยง: {clause.get('risk_level', '-')}**")
                st.markdown(f"**ข้อความในสัญญา:** {clause.get('clause_excerpt', '-')}")
                st.markdown(f"**ปัญหา:** {clause.get('issue', '-')}")
                if clause.get("counter_proposal"):
                    st.markdown(f"**ข้อเสนอแย้งที่แนะนำ:** {clause['counter_proposal']}")

with tab_obligations:
    obligations = db.get_obligations(contract_id)
    if not obligations:
        if st.button("📌 ดึงข้อผูกมัดทั้งหมดด้วย AI"):
            with st.spinner("กำลังดึงข้อผูกมัดจากสัญญา..."):
                try:
                    result = ai_engine.extract_obligations(contract["contract_text"])
                    db.add_obligations(contract_id, result.get("obligations", []))
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")
    else:
        STATUS_LABELS = {"pending": "⬜ ยังไม่เริ่ม", "in_progress": "🟡 กำลังดำเนินการ", "done": "✅ เสร็จสิ้น", "overdue": "🔴 เลยกำหนด"}
        for ob in obligations:
            with st.container(border=True):
                c1, c2 = st.columns([4, 2])
                c1.markdown(f"**{ob['obligation_text']}**")
                c1.caption(f"หมวด: {ob.get('category','-')} | ผู้รับผิดชอบ: {ob.get('responsible_party','-')} | กำหนด: {ob.get('due_date_or_trigger','-')}")
                if ob.get("penalty_if_missed"):
                    c1.caption(f"บทลงโทษหากพลาด: {ob['penalty_if_missed']}")
                new_status = c2.selectbox(
                    "สถานะ", list(STATUS_LABELS.keys()), format_func=lambda k: STATUS_LABELS[k],
                    index=list(STATUS_LABELS.keys()).index(ob["status"]) if ob["status"] in STATUS_LABELS else 0,
                    key=f"ob_status_{ob['id']}", label_visibility="collapsed",
                )
                if new_status != ob["status"]:
                    db.update_obligation_status(ob["id"], new_status)
                    st.rerun()
        if st.button("🔄 ดึงข้อผูกมัดใหม่ (เพิ่มต่อจากรายการเดิม)"):
            with st.spinner("กำลังดึงข้อผูกมัด..."):
                result = ai_engine.extract_obligations(contract["contract_text"])
                db.add_obligations(contract_id, result.get("obligations", []))
                st.rerun()

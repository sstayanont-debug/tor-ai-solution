"""หน้าวิเคราะห์ TOR ใหม่ — อัปโหลด/วาง TOR แล้วรัน AI pipeline: วิเคราะห์ TOR → ความเสี่ยง → โอกาสชนะงาน → เนื้อหาขาย"""

import io
import streamlit as st
import db
import ai_engine
import auth

user = auth.require_role(["admin", "sales"])
auth.sidebar_user_info()

st.title("📄 วิเคราะห์ TOR ใหม่")
st.caption("วางข้อความ TOR หรืออัปโหลดไฟล์ แล้วให้ AI วิเคราะห์แบบครบวงจร")


def extract_text_from_file(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    elif name.endswith(".docx"):
        import docx
        document = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs)
    else:
        return data.decode("utf-8", errors="ignore")


tab_paste, tab_upload = st.tabs(["✍️ วางข้อความ TOR", "📎 อัปโหลดไฟล์ (PDF/DOCX/TXT)"])

tor_text = ""
with tab_paste:
    pasted = st.text_area("วางเนื้อหา TOR ที่นี่", height=300, placeholder="คัดลอกเนื้อหาจากเอกสาร TOR มาวางที่นี่...")
    if pasted.strip():
        tor_text = pasted

with tab_upload:
    uploaded = st.file_uploader("เลือกไฟล์ TOR", type=["pdf", "docx", "txt"])
    if uploaded is not None:
        try:
            extracted = extract_text_from_file(uploaded)
            st.text_area("ข้อความที่สกัดได้ (ตรวจสอบก่อนวิเคราะห์)", value=extracted, height=250, key="extracted_preview")
            tor_text = st.session_state.get("extracted_preview", extracted)
        except Exception as e:
            st.error(f"อ่านไฟล์ไม่สำเร็จ: {e}")

st.divider()

col1, col2 = st.columns([3, 1])
project_name_override = col1.text_input("ชื่อโครงการ (ถ้าเว้นว่าง AI จะตั้งชื่อให้อัตโนมัติจาก TOR)")
full_pipeline = col2.checkbox("รันครบทุกขั้นตอน", value=True, help="วิเคราะห์ TOR + ประเมินความเสี่ยง + โอกาสชนะงาน + เนื้อหาขาย ในครั้งเดียว")

run = st.button("🚀 เริ่มวิเคราะห์ด้วย AI", type="primary", disabled=not tor_text.strip())

if run:
    company_profile = db.get_company_profile() or {}
    try:
        with st.spinner("กำลังวิเคราะห์ TOR ด้วย Claude..."):
            tor_analysis = ai_engine.analyze_tor(tor_text)

        name = project_name_override.strip() or tor_analysis.get("project_name") or "โครงการไม่ระบุชื่อ"
        project_id = db.create_project(name, tor_text, created_by_user_id=user["id"], department_id=user.get("department_id"))
        db.update_project(project_id, tor_analysis=tor_analysis, status="analyzing")
        db.log_audit(user["id"], user["email"], "create_project", "project", project_id, name)

        if full_pipeline:
            with st.spinner("กำลังประเมินความเสี่ยง..."):
                risk = ai_engine.assess_risk(tor_analysis, company_profile)
                db.update_project(project_id, risk_assessment=risk)

            with st.spinner("กำลังประเมินโอกาสชนะงาน..."):
                win_prob = ai_engine.estimate_win_probability(tor_analysis, risk, company_profile)
                db.update_project(project_id, win_probability=win_prob, status="ready")

            with st.spinner("กำลังสร้างเนื้อหาสนับสนุนการขาย..."):
                sales = ai_engine.generate_sales_support(tor_analysis, win_prob, company_profile)
                db.update_project(project_id, sales_support=sales)
        else:
            db.update_project(project_id, status="ready")

        st.success(f"วิเคราะห์เสร็จสมบูรณ์: {name}")
        st.session_state["selected_project_id"] = project_id
        st.switch_page("pages/3_โครงการทั้งหมด.py")

    except RuntimeError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดระหว่างเรียก AI: {e}")

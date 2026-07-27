"""หน้า Inbox TOR Watcher — สแกนอีเมลบริษัทหา TOR/RFP อัตโนมัติ แล้วนำเข้าเป็นโครงการด้วย AI"""

import streamlit as st
import db
import ai_engine
import auth
import email_watcher

current = auth.require_role(["admin", "sales"])
auth.sidebar_user_info()

st.title("📬 Inbox TOR Watcher")
st.caption(
    "สแกนอีเมลของบริษัท (ผ่าน Gmail API) หาข้อความ/ไฟล์แนบที่เข้าข่าย TOR หรือ RFP ที่ถูกส่งเข้ามา "
    "แล้วดึงมาเตรียมให้ AI วิเคราะห์ — แนะนำให้เชื่อมต่อด้วยอีเมลกลางของทีมขาย (เช่น sales@company.com) "
    "ไม่ใช่อีเมลส่วนตัว เพราะระบบจะสแกนเฉพาะอินบ็อกซ์ของบัญชีที่เชื่อมต่อเท่านั้น"
)

if not email_watcher.is_configured():
    st.warning(
        "⚙️ ยังไม่ได้ตั้งค่า Google Cloud OAuth (ไม่พบไฟล์ `credentials.json`) — "
        "กรุณาตั้งค่าตามขั้นตอนในหัวข้อ **Inbox TOR Watcher** ของ README.md ก่อนใช้งานฟีเจอร์นี้"
    )
    st.stop()

st.divider()

# ---------------- การเชื่อมต่อ Gmail ----------------
col1, col2 = st.columns([3, 1])
with col1:
    if email_watcher.is_connected():
        st.success("✅ เชื่อมต่อ Gmail แล้ว")
    else:
        st.info("ยังไม่ได้เชื่อมต่อ Gmail — กดปุ่มเชื่อมต่อเพื่อ authorize (จะเปิดหน้าต่างเบราว์เซอร์ให้ล็อกอิน)")
with col2:
    if email_watcher.is_connected():
        if st.button("🔌 ยกเลิกการเชื่อมต่อ"):
            email_watcher.disconnect()
            st.rerun()
    else:
        if st.button("🔗 เชื่อมต่อ Gmail", type="primary"):
            with st.spinner("กำลังเปิดหน้าต่างล็อกอิน Gmail... (ดูที่เบราว์เซอร์)"):
                try:
                    email_watcher.get_gmail_service()
                    st.success("เชื่อมต่อสำเร็จ")
                    st.rerun()
                except Exception as e:
                    st.error(f"เชื่อมต่อไม่สำเร็จ: {e}")

if not email_watcher.is_connected():
    st.stop()

st.divider()

# ---------------- ตั้งค่าการสแกน ----------------
st.subheader("🔍 สแกนหา TOR/RFP ใหม่")
c1, c2 = st.columns([3, 1])
keywords_text = c1.text_input(
    "คีย์เวิร์ดที่ใช้ค้นหา (คั่นด้วยจุลภาค)",
    value=", ".join(email_watcher.DEFAULT_KEYWORDS),
)
days = c2.number_input("ค้นย้อนหลัง (วัน)", min_value=1, max_value=90, value=7)

if st.button("🔍 สแกนอีเมลตอนนี้", type="primary"):
    with st.spinner("กำลังสแกนอีเมล..."):
        try:
            service = email_watcher.get_gmail_service()
            keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]
            found = email_watcher.search_tor_emails(service, keywords, int(days))
            new_count = 0
            for f in found:
                lead_id = db.upsert_email_lead(f["id"], f["from"], f["subject"], f["date"], f["attachment_names"])
                if lead_id:
                    new_count += 1
            st.success(f"สแกนเสร็จแล้ว พบอีเมลที่ตรงเงื่อนไข {len(found)} ฉบับ")
            st.rerun()
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดระหว่างสแกน: {e}")

st.divider()

# ---------------- รายการ leads ----------------
st.subheader("📋 รายการที่พบ")
tab_new, tab_history = st.tabs(["🆕 ใหม่ (รอตรวจสอบ)", "📜 ประวัติ"])

with tab_new:
    leads = db.list_email_leads(status="new")
    if not leads:
        st.info("ยังไม่มีรายการใหม่ — ลองกด 'สแกนอีเมลตอนนี้' ด้านบน")
    for lead in leads:
        with st.container(border=True):
            st.markdown(f"**{lead['subject'] or '(ไม่มีหัวข้อ)'}**")
            st.caption(f"จาก: {lead['sender']} | วันที่: {lead['received_at']}")
            st.caption(f"ไฟล์แนบ: {lead['attachment_names'] or '-'}")
            b1, b2, b3 = st.columns([1, 1, 3])
            if b1.button("📥 นำเข้าเป็นโครงการ", key=f"import_{lead['id']}", type="primary"):
                with st.spinner("กำลังดึงไฟล์แนบและวิเคราะห์ TOR ด้วย AI..."):
                    try:
                        service = email_watcher.get_gmail_service()
                        tor_text = email_watcher.extract_text_from_all_attachments(service, lead["gmail_message_id"])
                        if not tor_text.strip():
                            st.error("ไม่พบข้อความในไฟล์แนบ (อาจเป็นไฟล์สแกนภาพที่อ่านไม่ได้ หรือไม่ใช่ pdf/docx)")
                        else:
                            project_name = lead["subject"] or "โครงการจากอีเมล (ไม่มีหัวข้อ)"
                            project_id = db.create_project(
                                project_name, tor_text,
                                created_by_user_id=current["id"], department_id=current.get("department_id"),
                            )
                            tor_analysis = ai_engine.analyze_tor(tor_text)
                            db.update_project(project_id, tor_analysis=tor_analysis, status="analyzing")
                            db.update_email_lead_status(lead["id"], "imported", linked_project_id=project_id)
                            db.log_audit(current["id"], current["email"], "import_email_lead", "project", project_id, lead["subject"])
                            st.success(f"นำเข้าเป็นโครงการ '{project_name}' เรียบร้อย — ไปต่อที่หน้าโครงการทั้งหมดเพื่อประเมินความเสี่ยง/โอกาสชนะงาน")
                            st.rerun()
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาด: {e}")
            if b2.button("🗑️ ไม่สนใจ", key=f"dismiss_{lead['id']}"):
                db.update_email_lead_status(lead["id"], "dismissed")
                st.rerun()

with tab_history:
    imported = db.list_email_leads(status="imported")
    dismissed = db.list_email_leads(status="dismissed")
    st.markdown(f"**นำเข้าแล้ว:** {len(imported)} | **ไม่สนใจ:** {len(dismissed)}")
    for lead in imported + dismissed:
        with st.container(border=True):
            icon = "📥" if lead["status"] == "imported" else "🗑️"
            st.markdown(f"{icon} **{lead['subject'] or '(ไม่มีหัวข้อ)'}** — {lead['status']}")
            st.caption(f"จาก: {lead['sender']} | วันที่: {lead['received_at']}")

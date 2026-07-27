"""หน้าบริหารสัญญา — สำหรับโครงการที่ชนะงานแล้ว: แตก milestone จาก TOR ด้วย AI และติดตามความคืบหน้า"""

import streamlit as st
import db
import ai_engine
import auth

auth.require_role(["admin", "sales", "procurement"])
auth.sidebar_user_info()

STATUS_OPTIONS = {
    "won": "🏆 ชนะงาน",
    "contract_active": "📋 อยู่ระหว่างดำเนินสัญญา",
    "contract_completed": "✅ ปิดสัญญาแล้ว",
}
MILESTONE_STATUS = {
    "pending": "⬜ ยังไม่เริ่ม",
    "in_progress": "🟡 กำลังดำเนินการ",
    "done": "✅ เสร็จสิ้น",
    "delayed": "🔴 ล่าช้า",
}

st.title("📋 บริหารสัญญา")
st.caption("ติดตามงานหลังจากชนะการประมูล — แตก milestone จาก TOR และอัปเดตความคืบหน้า")

all_projects = db.list_projects()
contract_projects = [p for p in all_projects if p["status"] in STATUS_OPTIONS]

if not contract_projects:
    st.info("ยังไม่มีโครงการที่ชนะงาน — เมื่อโครงการใดชนะงาน ให้เปลี่ยนสถานะเป็น 'ชนะงาน' ในหน้าโครงการทั้งหมดก่อน")
    st.stop()

project_map = {p["name"]: p["id"] for p in contract_projects}
selected_name = st.selectbox("เลือกโครงการที่ชนะงาน", list(project_map.keys()))
project_id = project_map[selected_name]
project = db.get_project(project_id)

c1, c2 = st.columns([2, 1])
with c1:
    new_status = st.selectbox(
        "สถานะสัญญา", list(STATUS_OPTIONS.keys()),
        format_func=lambda k: STATUS_OPTIONS[k],
        index=list(STATUS_OPTIONS.keys()).index(project["status"]),
    )
    if new_status != project["status"]:
        db.update_project(project_id, status=new_status)
        st.rerun()

st.divider()

milestones = db.get_milestones(project_id)

if not milestones:
    st.warning("ยังไม่มี milestone สำหรับโครงการนี้")
    if st.button("🧩 แตก Milestone จาก TOR ด้วย AI", type="primary"):
        with st.spinner("กำลังวิเคราะห์และแตก milestone..."):
            try:
                result = ai_engine.extract_milestones(project.get("tor_analysis", {}), project.get("tor_text", ""))
                db.add_milestones(project_id, result.get("milestones", []))
                st.rerun()
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาด: {e}")
else:
    done = sum(1 for m in milestones if m["status"] == "done")
    st.progress(done / len(milestones) if milestones else 0, text=f"ความคืบหน้า: {done}/{len(milestones)} milestone เสร็จสิ้น")

    for m in milestones:
        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 2, 2])
            with c1:
                st.markdown(f"**{m['title']}**")
                st.caption(f"Deliverable: {m['deliverable']}")
                if m.get("due_date"):
                    st.caption(f"กำหนดส่ง: {m['due_date']}")
                if m.get("payment_percent"):
                    st.caption(f"สัดส่วนเบิกจ่าย: {m['payment_percent']}%" if m['payment_percent'].strip("%").replace(".", "").isdigit() else f"สัดส่วนเบิกจ่าย: {m['payment_percent']}")
            with c2:
                new_ms_status = st.selectbox(
                    "สถานะ", list(MILESTONE_STATUS.keys()),
                    format_func=lambda k: MILESTONE_STATUS[k],
                    index=list(MILESTONE_STATUS.keys()).index(m["status"]) if m["status"] in MILESTONE_STATUS else 0,
                    key=f"status_{m['id']}",
                    label_visibility="collapsed",
                )
                if new_ms_status != m["status"]:
                    db.update_milestone_status(m["id"], new_ms_status)
                    st.rerun()
            with c3:
                if st.button("🗑️ ลบ", key=f"del_{m['id']}"):
                    db.delete_milestone(m["id"])
                    st.rerun()
            notes = st.text_input("บันทึกเพิ่มเติม", value=m.get("notes", "") or "", key=f"notes_{m['id']}")
            if notes != (m.get("notes", "") or ""):
                db.update_milestone_status(m["id"], m["status"], notes)

    st.divider()
    if st.button("🔄 แตก Milestone ใหม่ (จะเพิ่มต่อจากรายการเดิม)"):
        with st.spinner("กำลังแตก milestone..."):
            result = ai_engine.extract_milestones(project.get("tor_analysis", {}), project.get("tor_text", ""))
            db.add_milestones(project_id, result.get("milestones", []))
            st.rerun()

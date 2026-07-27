"""หน้าจัดซื้อโครงการ (Procurement) — สร้าง RFQ จาก BOM, เทียบใบเสนอราคา vendor, ประเมินความเสี่ยงส่งมอบล่าช้า"""

import streamlit as st
import db
import ai_engine
import auth

auth.require_role(["admin", "procurement"])
auth.sidebar_user_info()

st.title("🧾 จัดซื้อโครงการ (Procurement / RFQ)")
st.caption(
    "ใช้สำหรับโครงการที่ชนะงานแล้ว — สร้างใบขอราคา (RFQ) จากรายการ BOM แล้ววาง/อัปโหลดใบเสนอราคาที่ได้รับจาก "
    "vendor แต่ละราย ให้ AI สกัดข้อมูลและเทียบให้ในตารางเดียว (ระบบยังไม่ส่งอีเมลหา vendor อัตโนมัติ)"
)

BID_STATUSES = {"won", "contract_active", "contract_completed"}
projects = [p for p in db.list_projects() if p["status"] in BID_STATUSES]

if not projects:
    st.info("ยังไม่มีโครงการที่ชนะงาน — เมื่อชนะงานแล้วเปลี่ยนสถานะโครงการเป็น 'ชนะงาน' ก่อน")
    st.stop()

project_map = {p["name"]: p["id"] for p in projects}
selected_name = st.selectbox("เลือกโครงการ", list(project_map.keys()))
project_id = project_map[selected_name]
project = db.get_project(project_id)

st.divider()

rfqs = db.get_rfqs_for_project(project_id)

with st.expander("➕ สร้าง RFQ ใหม่", expanded=not rfqs):
    bom = db.get_bom_for_project(project_id)
    title = st.text_input("ชื่อ RFQ", value=f"RFQ - {project['name']}")
    deadline = st.text_input("กำหนดให้ vendor ส่งราคากลับ")

    use_bom = False
    bom_items_selected = []
    if bom:
        bom_items = db.get_bom_items(bom["id"])
        procurable = [it for it in bom_items if it["category"] in ("hardware", "software", "subcontract", "license")]
        if procurable:
            use_bom = st.checkbox(f"ดึงรายการจาก BOM ของโครงการนี้ ({len(procurable)} รายการ: hardware/software/subcontract/license)", value=True)
            if use_bom:
                bom_items_selected = procurable
    else:
        st.caption("โครงการนี้ยังไม่มี BOM — ไปสร้างที่แท็บ BOM/ต้นทุน ในหน้าโครงการทั้งหมดได้ หรือกรอกรายการเองด้านล่าง")

    manual_items_text = st.text_area(
        "รายการเพิ่มเติม/รายการเอง (บรรทัดละ 1 รายการ รูปแบบ: ชื่อ, สเปค, จำนวน, หน่วย)",
        placeholder="เช่น: Server Rack 2U, CPU 16 core RAM 64GB, 2, เครื่อง",
    )

    if st.button("สร้าง RFQ", type="primary", disabled=not title.strip()):
        rfq_id = db.create_rfq(project_id, title, bom_id=bom["id"] if (bom and use_bom) else None, deadline=deadline)
        items_to_add = []
        for it in bom_items_selected:
            items_to_add.append({"item_name": it["item_name"], "spec": it["spec"], "qty": it["qty"], "unit": it["unit"]})
        for line in manual_items_text.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 1 and parts[0]:
                items_to_add.append({
                    "item_name": parts[0],
                    "spec": parts[1] if len(parts) > 1 else "",
                    "qty": float(parts[2]) if len(parts) > 2 and parts[2].replace(".", "", 1).isdigit() else 1,
                    "unit": parts[3] if len(parts) > 3 else "",
                })
        if items_to_add:
            db.add_rfq_items(rfq_id, items_to_add)
        st.success("สร้าง RFQ เรียบร้อย")
        st.rerun()

if not rfqs:
    st.stop()

st.divider()
rfq_map = {f"{r['title']} ({r['status']}) #{r['id']}": r["id"] for r in rfqs}
selected_rfq_label = st.selectbox("เลือก RFQ", list(rfq_map.keys()))
rfq_id = rfq_map[selected_rfq_label]
rfq = db.get_rfq(rfq_id)
rfq_items = db.get_rfq_items(rfq_id)

st.markdown(f"**สถานะ RFQ:** {rfq['status']}  |  **กำหนดส่งราคากลับ:** {rfq.get('deadline') or '-'}")

with st.expander("📋 รายการที่ขอราคา (RFQ items)"):
    for it in rfq_items:
        st.markdown(f"- **{it['item_name']}** — {it.get('spec', '-')} ({it['qty']} {it['unit']})")

st.subheader("📥 เพิ่มใบเสนอราคาจาก Vendor")
with st.form(f"add_quote_{rfq_id}"):
    c1, c2 = st.columns(2)
    vendor_name_freeform = c1.text_input("ชื่อ Vendor")
    raw_quote_text = st.text_area("วางเนื้อหาใบเสนอราคา (ราคา, ระยะเวลาส่งมอบ, เงื่อนไข SLA/ประกัน ฯลฯ)", height=180)
    submit_quote = st.form_submit_button("🤖 สกัดข้อมูลด้วย AI และเพิ่มเข้าตาราง")

if submit_quote and raw_quote_text.strip():
    with st.spinner("กำลังสกัดข้อมูลใบเสนอราคา..."):
        try:
            extracted = ai_engine.extract_quote_data(rfq_items, raw_quote_text)
            db.add_vendor_quote(rfq_id, {
                "vendor_name_freeform": vendor_name_freeform or extracted.get("vendor_name", ""),
                "raw_quote_text": raw_quote_text,
                "ai_extracted": extracted,
                "total_price": extracted.get("total_price"),
                "delivery_days": extracted.get("delivery_days"),
                "spec_match_percent": extracted.get("spec_match_percent"),
                "sla_delay_risk": extracted.get("sla_delay_risk", ""),
                "sla_risk_reason": extracted.get("sla_risk_reason", ""),
            })
            st.success("เพิ่มใบเสนอราคาเรียบร้อย")
            st.rerun()
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")

st.subheader("📊 เปรียบเทียบใบเสนอราคา")
quotes = db.get_vendor_quotes(rfq_id)
if not quotes:
    st.info("ยังไม่มีใบเสนอราคาสำหรับ RFQ นี้")
else:
    risk_icon = {"ต่ำ": "🟢", "ปานกลาง": "🟡", "สูง": "🔴"}
    for q in quotes:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
            name = q.get("vendor_name_freeform") or (q.get("ai_extracted") or {}).get("vendor_name", "ไม่ระบุ")
            c1.markdown(f"**{name}**")
            c1.caption(f"สถานะ: {q['status']}")
            c2.metric("ราคารวม", f"{q.get('total_price') or 0:,.0f}")
            c3.metric("ส่งมอบ (วัน)", q.get("delivery_days") or "-")
            c4.metric("ตรงสเปค", f"{q.get('spec_match_percent') or 0:.0f}%")
            risk = q.get("sla_delay_risk", "")
            c5.markdown(f"**ความเสี่ยงล่าช้า**  \n{risk_icon.get(risk, '')} {risk or '-'}")
            if q.get("sla_risk_reason"):
                st.caption(f"เหตุผล: {q['sla_risk_reason']}")
            extracted = q.get("ai_extracted") or {}
            if extracted.get("sla_terms"):
                st.caption(f"เงื่อนไข SLA: {extracted['sla_terms']}")
            if extracted.get("warranty"):
                st.caption(f"การรับประกัน: {extracted['warranty']}")
            if extracted.get("spec_match_notes"):
                st.caption(f"หมายเหตุความตรงสเปค: {extracted['spec_match_notes']}")
            b1, b2 = st.columns(2)
            if q["status"] != "selected":
                if b1.button("✅ เลือก vendor รายนี้", key=f"select_{q['id']}"):
                    db.select_vendor_quote(q["id"], rfq_id)
                    db.update_rfq_status(rfq_id, "awarded")
                    st.rerun()
            else:
                b1.success("เลือกแล้ว")

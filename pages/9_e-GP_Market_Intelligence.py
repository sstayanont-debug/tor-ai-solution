"""หน้า e-GP Market Intelligence — ค้นหาสัญญาภาครัฐที่ประมูลเสร็จแล้ว เพื่อวิเคราะห์คู่แข่ง/เบนช์มาร์กราคา"""

import streamlit as st
import db
import ai_engine
import auth
import egp_intelligence as egp

current = auth.require_role(["admin", "sales"])
auth.sidebar_user_info()

st.title("🏛️ e-GP Market Intelligence")
st.caption(
    "ดึงข้อมูลสัญญาจัดซื้อจัดจ้างภาครัฐที่ **ประมูลเสร็จแล้ว** จาก Open Data ทางการของกรมบัญชีกลาง "
    "(govspending.data.go.th) — ใช้ดูว่าใครเคยชนะงานประเภทไหน ราคาระดับไหน เพื่อประกอบการวิเคราะห์คู่แข่ง "
    "หรือเบนช์มาร์กราคาก่อนตั้งราคาเสนอ (ไม่ใช่ประกาศที่เปิดรับอยู่ตอนนี้)"
)

if not egp.is_configured():
    st.warning(
        "⚙️ ยังไม่ได้ตั้งค่า API key — กรุณาขอ API key ฟรีที่ "
        "[opend.data.go.th/register_api](https://opend.data.go.th/register_api) แล้วตั้งค่า `EGP_API_KEY` "
        "ในไฟล์ `.env` ตามขั้นตอนใน README.md หัวข้อ **e-GP Market Intelligence**"
    )
    st.stop()

st.info(
    "ℹ️ ยืนยัน field จากเอกสารทางการแล้ว — ชื่อผู้ชนะและราคาต่อสัญญาอยู่ในข้อมูลซ้อน (contract) "
    "ระบบดึงให้อัตโนมัติ แต่ถ้าโครงการมีหลายสัญญาย่อยจะแสดงเฉพาะสัญญาแรก กางดู **ข้อมูลดิบ (Raw JSON)** "
    "เพื่อดูทุกสัญญาได้"
)

st.divider()

# ---------------- ฟอร์มค้นหา ----------------
st.subheader("🔍 ค้นหาสัญญาที่ประมูลเสร็จแล้ว")
c1, c2, c3 = st.columns(3)
keyword = c1.text_input("คีย์เวิร์ด (ชื่อโครงการ/ประเภทงาน)", placeholder="เช่น ระบบ AI, ก่อสร้างอาคาร")
winner_tin = c2.text_input("เลขผู้เสียภาษีคู่แข่ง (ถ้าทราบ)", placeholder="เช่น 0105551000000")
dept_code = c3.text_input("รหัสหน่วยงาน (ถ้าทราบ)")

c4, c5, c6 = st.columns(3)
year = c4.text_input(
    "ปีงบประมาณ (พ.ศ.) — บังคับ",
    value=egp.current_thai_year(),
    help="พารามิเตอร์นี้ API บังคับต้องระบุ ถ้าเว้นว่างระบบจะใช้ปีปัจจุบันให้อัตโนมัติ",
)
budget_start = c5.text_input("งบประมาณต่ำสุด (บาท)")
budget_end = c6.text_input("งบประมาณสูงสุด (บาท)")

search_clicked = st.button("🔍 ค้นหา", type="primary", disabled=not (keyword or winner_tin or dept_code))

if search_clicked:
    with st.spinner("กำลังดึงข้อมูลจาก e-GP Open Data..."):
        try:
            result = egp.search_contracts(
                keyword=keyword, dept_code=dept_code, winner_tin=winner_tin,
                year=year, budget_start=budget_start, budget_end=budget_end,
            )
            st.session_state["egp_last_result"] = result
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")

result = st.session_state.get("egp_last_result")

if result:
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("จำนวนโครงการที่พบ", result.get("total_project", len(result.get("records", []))))
    if result.get("total_price"):
        c2.metric("มูลค่ารวม", result.get("total_price"))
    c3.metric("ปีงบประมาณที่ค้น", result.get("year_used", "-"))

    records = result.get("records", [])
    if not records:
        st.info("ไม่พบข้อมูลที่ตรงเงื่อนไข — ลองเปลี่ยนคีย์เวิร์ดหรือปีงบประมาณดู")
    for r in records:
        with st.container(border=True):
            st.markdown(f"**{r['project_name'] or '(ไม่มีชื่อโครงการ)'}**")
            st.caption(f"หน่วยงาน: {r['dept_name'] or '-'} | ประเภท: {r['project_type_name'] or '-'} | วิธีจัดซื้อ: {r['purchase_method_name'] or '-'}")
            cc1, cc2, cc3 = st.columns(3)
            cc1.markdown(f"👤 **ผู้ชนะ:** {r['winner'] or '(ไม่ทราบ — ดู raw JSON)'}")
            cc2.markdown(f"💰 **ราคา:** {r['price'] or '(ไม่ทราบ — ดู raw JSON)'}")
            cc3.markdown(f"📅 **วันที่:** {r['announce_date'] or '-'}")
            with st.expander("ข้อมูลดิบ (Raw JSON)"):
                st.json(r["raw"])

    st.divider()
    st.subheader("💾 บันทึกผลนี้เป็นข้อมูลคู่แข่งของโครงการ")
    st.caption("รวมผลการค้นหานี้เป็นข้อมูลคู่แข่ง แล้วให้ AI วิเคราะห์จุดข่ม เชื่อมเข้ากับแท็บ 'คู่แข่ง' ที่มีอยู่")

    projects_with_tor = [p for p in db.list_projects() if p.get("tor_analysis")]
    if not projects_with_tor:
        st.info("ยังไม่มีโครงการที่วิเคราะห์ TOR แล้ว — ไปวิเคราะห์ TOR ก่อนที่หน้า 'วิเคราะห์ TOR ใหม่'")
    else:
        proj_map = {p["name"]: p["id"] for p in projects_with_tor}
        selected_proj_name = st.selectbox("เลือกโครงการที่จะบันทึกข้อมูลคู่แข่งนี้เข้าไป", list(proj_map.keys()))
        competitor_name_input = st.text_input("ชื่อคู่แข่ง (สำหรับบันทึกในระบบ)", value=winner_tin or keyword)

        if st.button("💾 บันทึกเป็นคู่แข่ง + วิเคราะห์ด้วย AI", type="primary", disabled=not competitor_name_input.strip()):
            with st.spinner("กำลังบันทึกและวิเคราะห์..."):
                try:
                    project_id = proj_map[selected_proj_name]
                    project = db.get_project(project_id)
                    company_profile = db.get_company_profile() or {}
                    competitor_summary = egp.summarize_for_competitor(result)

                    analysis = ai_engine.analyze_competitor(
                        project.get("tor_analysis", {}), company_profile, competitor_summary
                    )
                    db.add_competitor(project_id, {
                        "competitor_name": competitor_name_input,
                        "estimated_bid_price": str(result.get("total_price", "")),
                        "past_win_rate": f"{result.get('total_project', len(records))} โครงการ (จากข้อมูล e-GP)",
                        "strengths": "", "weaknesses": "",
                        "source": "e-GP Open Data (govspending.data.go.th)",
                        "ai_differentiator_suggestions": analysis.get("differentiator_suggestions", ""),
                    })
                    db.log_audit(current["id"], current["email"], "add_competitor_from_egp", "project", project_id, competitor_name_input)
                    st.success(f"บันทึกข้อมูลคู่แข่ง '{competitor_name_input}' เข้าโครงการ '{selected_proj_name}' แล้ว — ไปดูที่แท็บคู่แข่งในหน้าโครงการทั้งหมด")
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")

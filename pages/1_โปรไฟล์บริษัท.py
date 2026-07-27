"""หน้าตั้งค่าโปรไฟล์บริษัท — ใช้เป็นข้อมูลประกอบการประเมินความเสี่ยง/โอกาสชนะงานของ AI"""

import streamlit as st
import db
import auth

auth.require_role(["admin"])
auth.sidebar_user_info()

st.title("🏢 โปรไฟล์บริษัท")
st.caption("ข้อมูลนี้จะถูกส่งให้ AI ใช้ประกอบการประเมินความเสี่ยงและโอกาสชนะงานในทุกโครงการ ยิ่งละเอียด ผลลัพธ์ยิ่งแม่นยำ")

profile = db.get_company_profile() or {}

with st.form("company_profile_form"):
    company_name = st.text_input("ชื่อบริษัท", value=profile.get("company_name", ""))

    col1, col2 = st.columns(2)
    with col1:
        experience_years = st.text_input(
            "ประสบการณ์ (ปี) / สาขาความเชี่ยวชาญ",
            value=profile.get("experience_years", ""),
            placeholder="เช่น 12 ปี ด้านระบบ IT ภาครัฐ",
        )
        team_size = st.text_input(
            "ขนาดทีม/กำลังคน",
            value=profile.get("team_size", ""),
            placeholder="เช่น พนักงานประจำ 45 คน, ทีมเทคนิค 20 คน",
        )
        financial_capacity = st.text_input(
            "ศักยภาพทางการเงิน",
            value=profile.get("financial_capacity", ""),
            placeholder="เช่น รายได้เฉลี่ย 150 ลบ./ปี วงเงินค้ำประกัน 20 ลบ.",
        )
    with col2:
        certifications = st.text_area(
            "ใบรับรอง/มาตรฐาน", value=profile.get("certifications", ""),
            placeholder="เช่น ISO 9001, ISO 27001, ผู้แทนจำหน่ายที่ได้รับอนุญาต",
            height=100,
        )
        core_competencies = st.text_area(
            "ความเชี่ยวชาญหลัก/จุดแข็ง", value=profile.get("core_competencies", ""),
            placeholder="เช่น ระบบ AI, Data Analytics, System Integration",
            height=100,
        )

    past_projects = st.text_area(
        "ผลงานที่ผ่านมา (โครงการเด่น, ลูกค้า, มูลค่างาน)",
        value=profile.get("past_projects", ""),
        placeholder="เช่น โครงการระบบบริหารจัดการข้อมูล กรม X มูลค่า 30 ลบ. (2567) ...",
        height=150,
    )

    submitted = st.form_submit_button("💾 บันทึกโปรไฟล์บริษัท", type="primary")
    if submitted:
        db.save_company_profile({
            "company_name": company_name,
            "experience_years": experience_years,
            "certifications": certifications,
            "past_projects": past_projects,
            "team_size": team_size,
            "financial_capacity": financial_capacity,
            "core_competencies": core_competencies,
        })
        st.success("บันทึกโปรไฟล์บริษัทเรียบร้อยแล้ว")

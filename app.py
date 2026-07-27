"""
TOR AI Solution — หน้าแรก (Dashboard)
แอปวิเคราะห์ TOR ประเมินความเสี่ยง โอกาสชนะงาน สนับสนุนการขาย และบริหารสัญญา
"""

import streamlit as st
import db
import auth

st.set_page_config(page_title="TOR AI Solution", page_icon="📊", layout="wide")
user = auth.require_login()

PAGE_ROLES = {
    "pages/1_โปรไฟล์บริษัท.py": ["admin"],
    "pages/2_วิเคราะห์TOR.py": ["admin", "sales"],
    "pages/3_โครงการทั้งหมด.py": ["admin", "sales", "procurement", "legal"],
    "pages/4_บริหารสัญญา.py": ["admin", "sales", "procurement"],
    "pages/5_จัดซื้อRFQ.py": ["admin", "procurement"],
    "pages/6_ตรวจสัญญา.py": ["admin", "legal"],
    "pages/7_จัดการผู้ใช้.py": ["admin"],
    "pages/8_TOR_จากอีเมล.py": ["admin", "sales"],
    "pages/9_e-GP_Market_Intelligence.py": ["admin", "sales"],
}

PAGE_META = {
    "pages/1_โปรไฟล์บริษัท.py": ("โปรไฟล์บริษัท", "🏢"),
    "pages/2_วิเคราะห์TOR.py": ("วิเคราะห์ TOR ใหม่", "📝"),
    "pages/3_โครงการทั้งหมด.py": ("โครงการทั้งหมด", "📁"),
    "pages/4_บริหารสัญญา.py": ("บริหารสัญญา", "📋"),
    "pages/5_จัดซื้อRFQ.py": ("จัดซื้อ / RFQ", "🧾"),
    "pages/6_ตรวจสัญญา.py": ("ตรวจสัญญา", "⚖️"),
    "pages/7_จัดการผู้ใช้.py": ("จัดการผู้ใช้", "👥"),
    "pages/8_TOR_จากอีเมล.py": ("TOR จากอีเมล", "📬"),
    "pages/9_e-GP_Market_Intelligence.py": ("e-GP Market Intelligence", "🏛️"),
}


def dashboard():
    auth.sidebar_user_info()

    STATUS_LABELS = {
        "analyzing": "🔵 กำลังวิเคราะห์",
        "ready": "🟢 พร้อมยื่นข้อเสนอ",
        "submitted": "🟡 ยื่นข้อเสนอแล้ว รอผล",
        "won": "🏆 ชนะงาน",
        "lost": "⚪ ไม่ได้งาน",
        "contract_active": "📋 อยู่ระหว่างดำเนินสัญญา",
        "contract_completed": "✅ ปิดสัญญาแล้ว",
    }

    st.title("📊 TOR AI Solution")
    st.caption("วิเคราะห์ TOR • ประเมินความเสี่ยง • ประเมินโอกาสชนะงาน • สนับสนุนการขาย • บริหารสัญญา")

    profile = db.get_company_profile()
    if not profile or not profile.get("company_name"):
        st.warning("ยังไม่ได้ตั้งค่าโปรไฟล์บริษัท กรุณาไปที่หน้า **โปรไฟล์บริษัท** ก่อน เพื่อให้ AI ประเมินผลได้แม่นยำขึ้น")

    projects = db.list_projects()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("โครงการทั้งหมด", len(projects))
    col2.metric("ชนะงานแล้ว", sum(1 for p in projects if p["status"] == "won" or p["status"].startswith("contract")))
    col3.metric("อยู่ระหว่างประมูล", sum(1 for p in projects if p["status"] in ("analyzing", "ready", "submitted")))
    col4.metric("ไม่ได้งาน", sum(1 for p in projects if p["status"] == "lost"))

    st.divider()

    if not projects:
        st.info("ยังไม่มีโครงการ — ไปที่หน้า **วิเคราะห์ TOR ใหม่** เพื่อเริ่มต้น")
    else:
        st.subheader("โครงการล่าสุด")
        for p in projects[:15]:
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 2, 1])
                c1.markdown(f"**{p['name']}**")
                c1.caption(f"อัปเดตล่าสุด: {p['updated_at'][:16].replace('T', ' ')}")
                c2.markdown(STATUS_LABELS.get(p["status"], p["status"]))
                if c3.button("เปิด", key=f"open_{p['id']}"):
                    st.session_state["selected_project_id"] = p["id"]
                    st.switch_page("pages/3_โครงการทั้งหมด.py")

    st.divider()
    st.caption(
        "เริ่มต้นใช้งาน: 1) ตั้งค่าโปรไฟล์บริษัท → 2) วิเคราะห์ TOR ใหม่ → "
        "3) ดูผลวิเคราะห์ความเสี่ยง/โอกาสชนะงาน/เนื้อหาขาย → 4) เมื่อชนะงาน ไปที่บริหารสัญญาเพื่อแตก milestone"
    )


def visible_pages():
    pages = []
    for path, roles in PAGE_ROLES.items():
        if user["role"] == "admin" or user["role"] in roles:
            title, icon = PAGE_META[path]
            pages.append(st.Page(path, title=title, icon=icon))
    return pages


home_page = st.Page(dashboard, title="หน้าแรก", icon="📊", default=True)
nav = st.navigation([home_page] + visible_pages())
nav.run()

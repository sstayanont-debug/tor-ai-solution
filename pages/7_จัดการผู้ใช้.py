"""หน้าจัดการผู้ใช้ (Admin only) — สร้าง/แก้ไข/ระงับผู้ใช้ กำหนด role และส่วนงาน จัดการส่วนงาน และดู audit log"""

import streamlit as st
import db
import auth

current = auth.require_role(["admin"])
auth.sidebar_user_info()

st.title("👥 จัดการผู้ใช้และสิทธิ์")

tab_users, tab_departments, tab_password, tab_audit = st.tabs(
    ["👤 ผู้ใช้งาน", "🏬 ส่วนงาน", "🔑 เปลี่ยนรหัสผ่าน", "📜 Audit Log"]
)

# ---------------- Users ----------------
with tab_users:
    departments = db.list_departments()
    dept_map = {d["name"]: d["id"] for d in departments}

    st.subheader("➕ เพิ่มผู้ใช้ใหม่")
    with st.form("add_user_form"):
        c1, c2 = st.columns(2)
        email = c1.text_input("อีเมล (ใช้ login)")
        name = c2.text_input("ชื่อ-นามสกุล")
        role = c1.selectbox("สิทธิ์ (Role)", auth.ALL_ROLES, format_func=lambda r: auth.ROLE_LABELS[r])
        dept_options = ["- ไม่ระบุ -"] + list(dept_map.keys())
        dept_choice = c2.selectbox("ส่วนงาน", dept_options)
        password = st.text_input("รหัสผ่านเริ่มต้น", type="password")
        submitted = st.form_submit_button("สร้างผู้ใช้", type="primary")

    if submitted:
        if not email.strip() or not password:
            st.error("กรุณากรอกอีเมลและรหัสผ่าน")
        elif db.get_user_by_email(email):
            st.error("อีเมลนี้มีผู้ใช้อยู่แล้ว")
        else:
            dept_id = dept_map.get(dept_choice)
            new_id = db.create_user(email, name, auth.hash_password(password), role, department_id=dept_id)
            db.log_audit(current["id"], current["email"], "create_user", "user", new_id, f"{email} / {role}")
            st.success(f"สร้างผู้ใช้ {email} เรียบร้อยแล้ว")
            st.rerun()

    st.divider()
    st.subheader("รายชื่อผู้ใช้ทั้งหมด")
    users = db.list_users()
    admin_count = sum(1 for u in users if u["role"] == "admin" and u["is_active"])

    for u in users:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([2.5, 1.5, 1.5, 1, 1])
            c1.markdown(f"**{u['name'] or '-'}**")
            c1.caption(u["email"])

            new_role = c2.selectbox(
                "Role", auth.ALL_ROLES, format_func=lambda r: auth.ROLE_LABELS[r],
                index=auth.ALL_ROLES.index(u["role"]) if u["role"] in auth.ALL_ROLES else 0,
                key=f"role_{u['id']}", label_visibility="collapsed",
            )
            dept_options2 = ["- ไม่ระบุ -"] + list(dept_map.keys())
            current_dept_name = next((n for n, i in dept_map.items() if i == u["department_id"]), "- ไม่ระบุ -")
            new_dept_choice = c3.selectbox(
                "ส่วนงาน", dept_options2, index=dept_options2.index(current_dept_name),
                key=f"dept_{u['id']}", label_visibility="collapsed",
            )
            is_self = u["id"] == current["id"]
            is_last_admin = u["role"] == "admin" and admin_count <= 1 and u["is_active"]

            new_active = c4.checkbox("ใช้งาน", value=bool(u["is_active"]), key=f"active_{u['id']}", disabled=is_last_admin)

            if c5.button("💾 บันทึก", key=f"save_user_{u['id']}"):
                if is_last_admin and (new_role != "admin" or not new_active):
                    st.error("ไม่สามารถลดสิทธิ์หรือระงับผู้ดูแลระบบคนสุดท้ายได้")
                else:
                    new_dept_id = dept_map.get(new_dept_choice)
                    db.update_user(u["id"], role=new_role, department_id=new_dept_id, is_active=1 if new_active else 0)
                    db.log_audit(current["id"], current["email"], "update_user", "user", u["id"], f"role={new_role}, active={new_active}")
                    st.success("บันทึกแล้ว")
                    st.rerun()

            if is_self:
                c1.caption("🫵 นี่คือบัญชีของคุณ")

# ---------------- Departments ----------------
with tab_departments:
    st.subheader("เพิ่มส่วนงานใหม่")
    with st.form("add_dept_form"):
        dept_name = st.text_input("ชื่อส่วนงาน", placeholder="เช่น ฝ่ายขายภาครัฐ, ฝ่ายจัดซื้อ IT")
        add_dept = st.form_submit_button("➕ เพิ่มส่วนงาน")
    if add_dept and dept_name.strip():
        db.create_department(dept_name.strip())
        st.success("เพิ่มส่วนงานแล้ว")
        st.rerun()

    st.divider()
    st.subheader("ส่วนงานทั้งหมด")
    for d in db.list_departments():
        st.markdown(f"- {d['name']}")

# ---------------- Change password ----------------
with tab_password:
    st.subheader("เปลี่ยนรหัสผ่านผู้ใช้")
    users2 = db.list_users()
    user_map = {f"{u['name']} ({u['email']})": u["id"] for u in users2}
    if user_map:
        selected_user_label = st.selectbox("เลือกผู้ใช้", list(user_map.keys()))
        target_user_id = user_map[selected_user_label]
        with st.form("change_password_form"):
            new_password = st.text_input("รหัสผ่านใหม่", type="password")
            confirm_password = st.text_input("ยืนยันรหัสผ่านใหม่", type="password")
            change_submitted = st.form_submit_button("🔑 เปลี่ยนรหัสผ่าน", type="primary")
        if change_submitted:
            if not new_password or new_password != confirm_password:
                st.error("รหัสผ่านไม่ตรงกัน หรือยังไม่ได้กรอก")
            else:
                db.update_user(target_user_id, password_hash=auth.hash_password(new_password))
                db.log_audit(current["id"], current["email"], "reset_password", "user", target_user_id)
                st.success("เปลี่ยนรหัสผ่านเรียบร้อยแล้ว")

# ---------------- Audit log ----------------
with tab_audit:
    st.subheader("ประวัติการใช้งานล่าสุด")
    logs = db.get_audit_log(limit=200)
    if not logs:
        st.info("ยังไม่มีประวัติการใช้งาน")
    for log in logs:
        st.caption(
            f"{log['created_at'][:19].replace('T', ' ')} — **{log['user_email'] or 'ไม่ทราบผู้ใช้'}** "
            f"ทำ `{log['action']}` ({log['entity_type']} #{log['entity_id']}) {log['details'] or ''}"
        )

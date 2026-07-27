"""
auth.py — ระบบ login, session, และ role-based access control (RBAC)
ไม่พึ่งพา library ภายนอก (ใช้ hashlib.pbkdf2 ของ stdlib) เพื่อลดความเสี่ยงเรื่องการติดตั้ง

วิธีใช้ในแต่ละหน้า (pages/*.py):
    import auth
    user = auth.require_role(["admin", "sales"])   # แสดงฟอร์ม login ให้อัตโนมัติถ้ายังไม่ login
                                                      # และเด้งข้อความ "ไม่มีสิทธิ์" ถ้า role ไม่ตรง
    auth.sidebar_user_info()                         # แสดงชื่อ/role + ปุ่ม logout ใน sidebar
"""

import os
import hashlib
import secrets

import streamlit as st
from dotenv import load_dotenv

import db

load_dotenv()

ROLE_LABELS = {
    "admin": "ผู้ดูแลระบบ",
    "sales": "ฝ่ายขาย",
    "procurement": "ฝ่ายจัดซื้อ",
    "legal": "ฝ่ายกฎหมาย/สัญญา",
}
ALL_ROLES = list(ROLE_LABELS.keys())

PBKDF2_ITERATIONS = 200_000


# ---------------- Password hashing (stdlib only, no bcrypt dependency) ----------------

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, hash_hex = stored_hash.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
        return secrets.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ---------------- Bootstrap ----------------

def bootstrap():
    """เรียกทุกครั้งที่โหลดหน้า — สร้างตารางถ้ายังไม่มี และสร้าง admin เริ่มต้นถ้ายังไม่มี user เลย"""
    db.init_db()
    if db.count_users() == 0:
        email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@company.local")
        password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "ChangeMe123!")
        db.ensure_default_admin(email, "ผู้ดูแลระบบ (ค่าเริ่มต้น)", hash_password(password))


# ---------------- Session helpers ----------------

def current_user():
    return st.session_state.get("auth_user")


def _set_session_user(user_row: dict):
    st.session_state["auth_user"] = {
        "id": user_row["id"],
        "email": user_row["email"],
        "name": user_row["name"],
        "role": user_row["role"],
        "department_id": user_row["department_id"],
    }


def login_form():
    st.title("🔐 เข้าสู่ระบบ")
    st.caption("TOR AI Solution — ระบบสำหรับผู้ใช้ภายในองค์กรเท่านั้น")
    with st.form("login_form"):
        email = st.text_input("อีเมล")
        password = st.text_input("รหัสผ่าน", type="password")
        submitted = st.form_submit_button("เข้าสู่ระบบ", type="primary")
    if submitted:
        user = db.get_user_by_email(email)
        if user and user["is_active"] and verify_password(password, user["password_hash"]):
            _set_session_user(user)
            db.log_audit(user["id"], user["email"], "login", "user", user["id"])
            st.rerun()
        else:
            st.error("อีเมลหรือรหัสผ่านไม่ถูกต้อง หรือบัญชีถูกระงับการใช้งาน")

    with st.expander("ℹ️ เข้าสู่ระบบครั้งแรก / ยังไม่มีบัญชี"):
        st.write(
            "ผู้ดูแลระบบคนแรกถูกสร้างอัตโนมัติจากค่าใน `.env` "
            "(`DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD`) — ถ้ายังไม่ได้ตั้งค่า จะใช้ค่าเริ่มต้น "
            "`admin@company.local` / `ChangeMe123!` **ควรเข้าสู่ระบบแล้วเปลี่ยนรหัสผ่านทันทีที่หน้า จัดการผู้ใช้**"
        )


def require_login():
    bootstrap()
    if not current_user():
        login_form()
        st.stop()
    return current_user()


def require_role(allowed_roles):
    """เรียกที่บนสุดของแต่ละหน้า — บังคับ login และเช็คสิทธิ์ role (admin ผ่านได้ทุกหน้าเสมอ)"""
    user = require_login()
    if user["role"] != "admin" and user["role"] not in allowed_roles:
        st.error(
            f"🚫 คุณไม่มีสิทธิ์เข้าถึงหน้านี้ (สิทธิ์ของคุณ: {ROLE_LABELS.get(user['role'], user['role'])}) "
            "กรุณาติดต่อผู้ดูแลระบบหากต้องการสิทธิ์เพิ่มเติม"
        )
        sidebar_user_info()
        st.stop()
    return user


def logout():
    user = current_user()
    if user:
        db.log_audit(user["id"], user["email"], "logout", "user", user["id"])
    st.session_state.pop("auth_user", None)


def sidebar_user_info():
    user = current_user()
    if not user:
        return
    with st.sidebar:
        st.divider()
        dept = db.get_department(user["department_id"]) if user.get("department_id") else None
        dept_label = dept["name"] if dept else "-"
        st.markdown(f"👤 **{user['name']}**")
        st.caption(f"{ROLE_LABELS.get(user['role'], user['role'])} • {dept_label}")
        if st.button("🚪 ออกจากระบบ", use_container_width=True):
            logout()
            st.rerun()

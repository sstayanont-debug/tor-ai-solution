"""
gmail_web_oauth_fix.py — แปลง Inbox TOR Watcher จาก Desktop OAuth (ใช้ได้แค่บนเครื่อง)
ไปเป็น Web OAuth (ใช้ได้ทั้งบนเครื่องและบนคลาวด์) + ย้ายที่เก็บ token จากไฟล์ไปเป็นฐานข้อมูล

รันครั้งเดียวที่โฟลเดอร์ tor-ai-solution: python3 gmail_web_oauth_fix.py
"""
import re

CHANGED = []
SKIPPED = []


def patch_file(path, replacements):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for old, new, label in replacements:
        if old in content:
            content = content.replace(old, new, 1)
            CHANGED.append(f"{path}: {label}")
        else:
            SKIPPED.append(f"{path}: {label} (ไม่พบข้อความเดิม — อาจแก้ไปแล้ว)")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# 1) db.py — เพิ่มคอลัมน์เก็บ gmail token + ฟังก์ชัน get/set/clear
# ---------------------------------------------------------------------------
db_replacements = [
    (
        '        _ensure_column(conn, "projects", "created_by_user_id", "INTEGER")\n',
        '        _ensure_column(conn, "projects", "created_by_user_id", "INTEGER")\n'
        '        _ensure_column(conn, "company_profile", "gmail_token_json", "TEXT")\n',
        "เพิ่มคอลัมน์ gmail_token_json ใน company_profile",
    ),
    (
        "# -------------------- Projects --------------------",
        '''def get_gmail_token() -> str:
    """ดึง Gmail OAuth token (JSON string) ที่เก็บไว้ในฐานข้อมูล — ใช้แทนไฟล์ เพราะไฟล์บนคลาวด์ไม่ persist"""
    with get_conn() as conn:
        row = conn.execute("SELECT gmail_token_json FROM company_profile WHERE id = 1").fetchone()
        return row["gmail_token_json"] if row and row["gmail_token_json"] else None


def set_gmail_token(token_json: str):
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM company_profile WHERE id = 1").fetchone()
        if existing:
            conn.execute("UPDATE company_profile SET gmail_token_json=? WHERE id=1", (token_json,))
        else:
            conn.execute("INSERT INTO company_profile (id, gmail_token_json) VALUES (1, ?)", (token_json,))


def clear_gmail_token():
    with get_conn() as conn:
        conn.execute("UPDATE company_profile SET gmail_token_json=NULL WHERE id=1")


# -------------------- Projects --------------------''',
        "เพิ่มฟังก์ชัน get_gmail_token / set_gmail_token / clear_gmail_token",
    ),
]

# ---------------------------------------------------------------------------
# 2) email_watcher.py — เปลี่ยนเป็น Web OAuth flow, เก็บ token ในฐานข้อมูล
# ---------------------------------------------------------------------------
email_watcher_replacements = [
    (
        '''def is_configured() -> bool:
    """มีไฟล์ credentials.json (OAuth client) วางไว้แล้วหรือยัง"""
    return os.path.exists(CREDENTIALS_PATH)''',
        '''def is_configured() -> bool:
    """มี OAuth client ตั้งค่าไว้แล้วหรือยัง (จาก environment variable แบบ Web OAuth หรือไฟล์ credentials.json แบบเก่า)"""
    if os.environ.get("GOOGLE_OAUTH_CLIENT_ID") and os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"):
        return True
    return os.path.exists(CREDENTIALS_PATH)''',
        "แก้ is_configured() ให้เช็ค env var แบบ Web OAuth ด้วย",
    ),
    (
        '''def is_connected() -> bool:
    """เคย authorize บัญชี Gmail แล้วหรือยัง (มี token เก็บไว้)"""
    return os.path.exists(TOKEN_PATH)


def disconnect():
    if os.path.exists(TOKEN_PATH):
        os.remove(TOKEN_PATH)''',
        '''def is_connected() -> bool:
    """เคย authorize บัญชี Gmail แล้วหรือยัง (เช็คจาก token ที่เก็บในฐานข้อมูล)"""
    import db
    return bool(db.get_gmail_token())


def disconnect():
    import db
    db.clear_gmail_token()


def _get_client_config():
    """อ่านค่า OAuth client (id/secret) แบบ Web application จาก environment variable
    (ตั้งค่าใน .env ตอนรันบนเครื่อง หรือ Secrets ตอน deploy บนคลาวด์) — ใช้แทน credentials.json แบบ Desktop app เดิม"""
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if client_id and client_secret:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
    return None


def get_authorization_url(redirect_uri: str):
    """สร้างลิงก์ให้ผู้ใช้กดไปอนุญาต Gmail — เปิดแท็บใหม่ แล้ว Google จะ redirect กลับมาที่ redirect_uri พร้อม ?code=..."""
    from google_auth_oauthlib.flow import Flow

    client_config = _get_client_config()
    if not client_config:
        raise RuntimeError(
            "ไม่พบ GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET "
            "กรุณาตั้งค่าใน .env (รันบนเครื่อง) หรือ Secrets (รันบนคลาวด์) ก่อน"
        )
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    auth_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    return auth_url, state


def exchange_code_for_token(code: str, redirect_uri: str):
    """แลก authorization code ที่ได้จากการ redirect กลับมา เป็น token แล้วบันทึกลงฐานข้อมูล"""
    import db
    from google_auth_oauthlib.flow import Flow

    client_config = _get_client_config()
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    db.set_gmail_token(flow.credentials.to_json())''',
        "แก้ is_connected/disconnect ให้ใช้ฐานข้อมูล + เพิ่มฟังก์ชัน Web OAuth flow",
    ),
    (
        '''def get_gmail_service():
    """สร้าง Gmail API client — ถ้ายังไม่เคย authorize จะเปิดเบราว์เซอร์ให้ล็อกอิน (ใช้ได้เมื่อรันแอปบนเครื่อง/เซิร์ฟเวอร์ที่มีเบราว์เซอร์เข้าถึงได้)"""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    if not is_configured():
        raise RuntimeError(
            "ไม่พบไฟล์ credentials.json — กรุณาตั้งค่า Google Cloud OAuth ก่อน (ดูขั้นตอนใน README.md)"
        )

    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)''',
        '''def get_gmail_service():
    """สร้าง Gmail API client จาก token ที่เชื่อมต่อไว้แล้ว (ต้องเชื่อมต่อผ่านหน้าเว็บก่อน — ดู get_authorization_url)"""
    import json
    import db
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_json = db.get_gmail_token()
    if not token_json:
        raise RuntimeError("ยังไม่ได้เชื่อมต่อ Gmail — กรุณากดปุ่ม 'เชื่อมต่อ Gmail' ก่อน")

    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            db.set_gmail_token(creds.to_json())
        else:
            raise RuntimeError("การเชื่อมต่อ Gmail หมดอายุ กรุณากดปุ่ม 'เชื่อมต่อ Gmail' ใหม่อีกครั้ง")

    return build("gmail", "v1", credentials=creds)''',
        "แก้ get_gmail_service() ให้อ่าน token จากฐานข้อมูลแทนไฟล์",
    ),
]

# ---------------------------------------------------------------------------
# 3) pages/8_TOR_จากอีเมล.py — เปลี่ยน UI ส่วนเชื่อมต่อ Gmail เป็นแบบ redirect link
# ---------------------------------------------------------------------------
page8_path = "pages/8_TOR_จากอีเมล.py"
page8_replacements = [
    (
        "import streamlit as st\n",
        "import os\nimport streamlit as st\n",
        "เพิ่ม import os",
    ),
    (
        '''# ------------------- การเชื่อมต่อ Gmail -------------------
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
    st.stop()''',
        '''# ------------------- การเชื่อมต่อ Gmail (Web OAuth — ใช้ได้ทั้งบนเครื่องและบนคลาวด์) -------------------
REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8501")

qp = st.query_params
if "code" in qp and not email_watcher.is_connected():
    try:
        email_watcher.exchange_code_for_token(qp["code"], REDIRECT_URI)
        st.query_params.clear()
        st.success("เชื่อมต่อ Gmail สำเร็จ")
        st.rerun()
    except Exception as e:
        st.error(f"เชื่อมต่อไม่สำเร็จ: {e}")

col1, col2 = st.columns([3, 1])
with col1:
    if email_watcher.is_connected():
        st.success("✅ เชื่อมต่อ Gmail แล้ว")
    else:
        st.info("ยังไม่ได้เชื่อมต่อ Gmail — กดปุ่มเชื่อมต่อ จะเปิดแท็บใหม่ให้ล็อกอิน Gmail แล้วกลับมาหน้านี้อัตโนมัติ")
with col2:
    if email_watcher.is_connected():
        if st.button("🔌 ยกเลิกการเชื่อมต่อ"):
            email_watcher.disconnect()
            st.rerun()
    else:
        try:
            auth_url, _state = email_watcher.get_authorization_url(REDIRECT_URI)
            st.link_button("🔗 เชื่อมต่อ Gmail", auth_url, type="primary")
        except Exception as e:
            st.error(f"ตั้งค่าไม่ครบ: {e}")

if not email_watcher.is_connected():
    st.stop()''',
        "เปลี่ยน UI เชื่อมต่อ Gmail เป็นแบบ redirect link (Web OAuth)",
    ),
]

patch_file("db.py", db_replacements)
patch_file("email_watcher.py", email_watcher_replacements)
patch_file(page8_path, page8_replacements)

print("=== แก้ไขสำเร็จ ===")
for c in CHANGED:
    print("✅", c)
if SKIPPED:
    print("\n=== ข้ามไป (ตรวจสอบด้วย) ===")
    for s in SKIPPED:
        print("⚠️ ", s)

"""
gmail_web_oauth_fix4.py — แก้ปัญหา "(invalid_grant) Missing code verifier"
สาเหตุ: get_authorization_url() กับ exchange_code_for_token() สร้าง Flow object คนละตัวกัน
ทำให้ PKCE code_verifier ที่สุ่มไว้ตอนขอ auth URL หายไปตอนแลก code
วิธีแก้: สร้าง code_verifier เอง แล้วส่งผ่านพารามิเตอร์ "state" (Google จะสะท้อนค่ากลับมาให้เป๊ะๆ)
เพื่อให้ตอนแลก code เอา state กลับมาใช้เป็น code_verifier ตัวเดิมได้

รันครั้งเดียวที่โฟลเดอร์ tor-ai-solution: python3 gmail_web_oauth_fix4.py
"""

CHANGED = []
SKIPPED = []


def patch_file(path, replacements):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for old, new, label in replacements:
        if new.strip() in content:
            SKIPPED.append(f"{path}: {label} (ดูเหมือนแก้ไปแล้ว)")
            continue
        if old in content:
            content = content.replace(old, new, 1)
            CHANGED.append(f"{path}: {label}")
        else:
            SKIPPED.append(f"{path}: {label} (ไม่พบข้อความเดิม — กรุณาแจ้งเพื่อตรวจสอบ)")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# 1) email_watcher.py — แก้ get_authorization_url / exchange_code_for_token
# ---------------------------------------------------------------------------
old_auth_url_func = '''def get_authorization_url(redirect_uri: str):
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
    return auth_url, state'''

new_auth_url_func = '''def get_authorization_url(redirect_uri: str):
    """สร้างลิงก์ให้ผู้ใช้กดไปอนุญาต Gmail — เปิดแท็บใหม่ แล้ว Google จะ redirect กลับมาที่ redirect_uri พร้อม ?code=...&state=...
    หมายเหตุ: สุ่ม code_verifier (PKCE) เองแล้วฝากไปกับพารามิเตอร์ state เพราะ Google จะสะท้อนค่า state
    กลับมาให้เป๊ะๆ ตอน redirect กลับ — ใช้แทนการเก็บ state ไว้ในเครื่อง (ซึ่งอาจหายไปเพราะเปิดคนละ request/instance)"""
    import secrets
    from google_auth_oauthlib.flow import Flow

    client_config = _get_client_config()
    if not client_config:
        raise RuntimeError(
            "ไม่พบ GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET "
            "กรุณาตั้งค่าใน .env (รันบนเครื่อง) หรือ Secrets (รันบนคลาวด์) ก่อน"
        )
    code_verifier = secrets.token_urlsafe(64)
    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=redirect_uri, code_verifier=code_verifier
    )
    auth_url, _state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent", state=code_verifier
    )
    return auth_url, code_verifier'''

old_exchange_func = '''def exchange_code_for_token(code: str, redirect_uri: str):
    """แลก authorization code ที่ได้จากการ redirect กลับมา เป็น token แล้วบันทึกลงฐานข้อมูล"""
    import db
    from google_auth_oauthlib.flow import Flow

    client_config = _get_client_config()
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri, state=state)
    flow.fetch_token(code=code)
    db.set_gmail_token(flow.credentials.to_json())'''

new_exchange_func = '''def exchange_code_for_token(code: str, state: str, redirect_uri: str):
    """แลก authorization code ที่ได้จากการ redirect กลับมา เป็น token แล้วบันทึกลงฐานข้อมูล
    ต้องส่ง state ที่ Google ส่งกลับมาด้วย (ใช้เป็น code_verifier ตัวเดิมที่สุ่มไว้ตอน get_authorization_url)"""
    import db
    from google_auth_oauthlib.flow import Flow

    client_config = _get_client_config()
    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=redirect_uri, code_verifier=state
    )
    flow.fetch_token(code=code)
    db.set_gmail_token(flow.credentials.to_json())'''

email_watcher_replacements = [
    (old_auth_url_func, new_auth_url_func, "แก้ get_authorization_url() ให้สร้าง+ฝาก code_verifier ผ่าน state"),
    (old_exchange_func, new_exchange_func, "แก้ exchange_code_for_token() ให้รับ state และใช้เป็น code_verifier"),
]
patch_file("email_watcher.py", email_watcher_replacements)


# ---------------------------------------------------------------------------
# 2) app.py — ส่ง state ไปด้วยตอนเรียก exchange_code_for_token
# ---------------------------------------------------------------------------
old_call = 'email_watcher.exchange_code_for_token(_qp["code"], _redirect_uri)'
new_call = 'email_watcher.exchange_code_for_token(_qp["code"], _qp.get("state", ""), _redirect_uri)'
patch_file("app.py", [(old_call, new_call, "ส่ง state ไปด้วยตอนแลก code")])


# ---------------------------------------------------------------------------
# 3) pages/8_TOR_จากอีเมล.py — จุดนี้เป็นโค้ดที่ไม่ถูกเรียกใช้แล้วจริงๆ (app.py จัดการก่อน)
#    แต่แก้ให้ signature ตรงกันไว้เผื่อ เพื่อความสะอาดของโค้ด
# ---------------------------------------------------------------------------
old_page8_call = 'email_watcher.exchange_code_for_token(qp["code"], REDIRECT_URI)'
new_page8_call = 'email_watcher.exchange_code_for_token(qp["code"], qp.get("state", ""), REDIRECT_URI)'
patch_file("pages/8_TOR_จากอีเมล.py", [(old_page8_call, new_page8_call, "ส่ง state ไปด้วย (โค้ดสำรอง)")])


print("=== สรุปผล ===")
for c in CHANGED:
    print("✅", c)
if SKIPPED:
    print("\n=== ข้าม/ตรวจสอบ ===")
    for s in SKIPPED:
        print("⚠️ ", s)

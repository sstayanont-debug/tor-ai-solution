"""
email_watcher.py — Inbox TOR Watcher
สแกนอีเมล (Gmail) ของบริษัทหา TOR/RFP ที่ถูกส่งเข้ามา แล้วดึงไฟล์แนบมาเตรียมวิเคราะห์

ใช้ Gmail API โดยตรง (ไม่พึ่ง MCP/connector ของ Claude) เพื่อให้แอปทำงานได้อิสระเวลา deploy จริง
บนเซิร์ฟเวอร์ของบริษัทเอง โดยไม่ต้องพึ่งเซสชันแชทใดๆ

ก่อนใช้งานต้องตั้งค่า Google Cloud OAuth ก่อน (ดูขั้นตอนใน README.md หัวข้อ "Inbox TOR Watcher")
แนะนำให้ authorize ด้วยอีเมลกลางของทีมขาย/บริษัท (เช่น sales@company.com) ไม่ใช่อีเมลส่วนตัว
เพราะแอปจะสแกนอินบ็อกซ์ของบัญชีที่ authorize เท่านั้น
"""

import os
import base64
import io

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "data", "gmail_token.json")

DEFAULT_KEYWORDS = [
    "TOR", "RFP", "เชิญยื่นข้อเสนอ", "ขอบเขตงาน", "ประกวดราคา", "ขอเสนอราคา", "Terms of Reference",
]


def is_configured() -> bool:
    """มี OAuth client ตั้งค่าไว้แล้วหรือยัง (จาก environment variable แบบ Web OAuth หรือไฟล์ credentials.json แบบเก่า)"""
    if os.environ.get("GOOGLE_OAUTH_CLIENT_ID") and os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"):
        return True
    return os.path.exists(CREDENTIALS_PATH)


def is_connected() -> bool:
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
    return auth_url, code_verifier


def exchange_code_for_token(code: str, state: str, redirect_uri: str):
    """แลก authorization code ที่ได้จากการ redirect กลับมา เป็น token แล้วบันทึกลงฐานข้อมูล
    ต้องส่ง state ที่ Google ส่งกลับมาด้วย (ใช้เป็น code_verifier ตัวเดิมที่สุ่มไว้ตอน get_authorization_url)"""
    import db
    from google_auth_oauthlib.flow import Flow

    client_config = _get_client_config()
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri, code_verifier=state)
    flow.fetch_token(code=code)
    db.set_gmail_token(flow.credentials.to_json())

def get_gmail_service():
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

    return build("gmail", "v1", credentials=creds)


def build_query(keywords: list, days: int) -> str:
    kw_query = " OR ".join(f'"{k}"' for k in keywords if k.strip())
    return f"has:attachment ({kw_query}) newer_than:{days}d"


def search_tor_emails(service, keywords: list, days: int, max_results: int = 30):
    """ค้นหาอีเมลที่มีไฟล์แนบและตรงคีย์เวิร์ด คืนค่ารายการ metadata (ยังไม่โหลดไฟล์แนบ)"""
    query = build_query(keywords, days)
    results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = results.get("messages", [])
    detailed = []
    for m in messages:
        msg = service.users().messages().get(
            userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        attachments = _list_attachment_names(msg.get("payload", {}))
        detailed.append({
            "id": m["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "attachment_names": attachments,
        })
    return detailed


def _list_attachment_names(payload, names=None):
    if names is None:
        names = []
    if payload.get("filename"):
        names.append(payload["filename"])
    for part in payload.get("parts", []) or []:
        _list_attachment_names(part, names)
    return names


def download_attachments(service, message_id: str):
    """โหลดไฟล์แนบที่เป็น .pdf/.docx ของอีเมลนี้ คืนค่า list ของ (filename, bytes)"""
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = msg.get("payload", {})
    results = []

    def walk(part):
        filename = part.get("filename", "")
        body = part.get("body", {})
        if filename and filename.lower().endswith((".pdf", ".docx")):
            att_id = body.get("attachmentId")
            if att_id:
                att = service.users().messages().attachments().get(
                    userId="me", messageId=message_id, id=att_id
                ).execute()
                data = base64.urlsafe_b64decode(att["data"])
                results.append((filename, data))
        for p in part.get("parts", []) or []:
            walk(p)

    walk(payload)
    return results


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    try:
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        elif name.endswith(".docx"):
            import docx
            document = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in document.paragraphs)
    except Exception:
        return ""
    return ""


def extract_text_from_all_attachments(service, message_id: str) -> str:
    """ดึงและรวมข้อความจากไฟล์แนบทั้งหมดของอีเมล (เผื่อ TOR แยกเป็นหลายไฟล์)"""
    attachments = download_attachments(service, message_id)
    chunks = []
    for filename, data in attachments:
        text = extract_text(filename, data)
        if text.strip():
            chunks.append(f"--- ไฟล์แนบ: {filename} ---\n{text}")
    return "\n\n".join(chunks)

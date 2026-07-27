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
    """มีไฟล์ credentials.json (OAuth client) วางไว้แล้วหรือยัง"""
    return os.path.exists(CREDENTIALS_PATH)


def is_connected() -> bool:
    """เคย authorize บัญชี Gmail แล้วหรือยัง (มี token เก็บไว้)"""
    return os.path.exists(TOKEN_PATH)


def disconnect():
    if os.path.exists(TOKEN_PATH):
        os.remove(TOKEN_PATH)


def get_gmail_service():
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

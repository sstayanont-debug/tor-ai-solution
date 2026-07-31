"""
gmail_web_oauth_fix5.py — แก้ exchange_code_for_token() ส่วนที่เหลือจากรอบก่อน (ข้ามไปเพราะข้อความไม่ตรง)
ใช้เลขบรรทัดอ้างอิงแทนการจับคู่ข้อความ

รันครั้งเดียวที่โฟลเดอร์ tor-ai-solution: python3 gmail_web_oauth_fix5.py
"""
with open("email_watcher.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

start = None
for i, line in enumerate(lines):
    if line.strip().startswith("def exchange_code_for_token"):
        start = i
        break

if start is None:
    print("⚠️ ไม่พบ def exchange_code_for_token — อาจแก้ไปแล้ว")
elif "state: str" in lines[start]:
    print("ฟังก์ชันนี้แก้ไปแล้ว (มี state: str อยู่แล้ว) ข้ามการแก้ซ้ำ")
else:
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("def "):
            end = j
            break

    new_func = '''def exchange_code_for_token(code: str, state: str, redirect_uri: str):
    """แลก authorization code ที่ได้จากการ redirect กลับมา เป็น token แล้วบันทึกลงฐานข้อมูล
    ต้องส่ง state ที่ Google ส่งกลับมาด้วย (ใช้เป็น code_verifier ตัวเดิมที่สุ่มไว้ตอน get_authorization_url)"""
    import db
    from google_auth_oauthlib.flow import Flow

    client_config = _get_client_config()
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri, code_verifier=state)
    flow.fetch_token(code=code)
    db.set_gmail_token(flow.credentials.to_json())

'''
    new_lines = lines[:start] + [new_func] + lines[end:]
    with open("email_watcher.py", "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print(f"✅ แทนที่บรรทัด {start+1}-{end} ด้วยฟังก์ชัน exchange_code_for_token ใหม่แล้ว")

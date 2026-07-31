"""
gmail_web_oauth_fix3.py — แก้ app.py ให้ประมวลผล Gmail OAuth callback (?code=...) ได้
ไม่ว่า Google จะ redirect กลับมาที่หน้าไหนก็ตาม (เพราะ redirect_uri ตั้งเป็นหน้าแรกเสมอ
แต่ st.navigation ทำให้แต่ละหน้ามี URL แยกกัน โค้ดเดิมใน pages/8 เลยไม่เคยถูกเรียกตอน redirect กลับมา)

รันครั้งเดียวที่โฟลเดอร์ tor-ai-solution: python3 gmail_web_oauth_fix3.py
"""

path = "app.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

anchor = 'user = auth.require_login()'

if "_qp = st.query_params" in content:
    print("app.py: แก้ไปแล้ว ข้ามการแก้ซ้ำ")
elif anchor not in content:
    print("⚠️  ไม่พบบรรทัด 'user = auth.require_login()' ใน app.py — กรุณาแจ้งเพื่อตรวจสอบ")
else:
    insertion = '''import os
import email_watcher

# ---- ประมวลผล Gmail OAuth callback ก่อนเช็ค login ----
# Google จะ redirect กลับมาที่ URL หน้าแรกเสมอ (ตาม redirect_uri ที่ตั้งไว้ตอนสร้าง OAuth client)
# โค้ดส่วนนี้ต้องอยู่ก่อน require_login() และทำงานทุกครั้งที่แอปโหลด ไม่ว่าจะอยู่หน้าไหน
_qp = st.query_params
if "code" in _qp:
    _redirect_uri = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8501")
    try:
        email_watcher.exchange_code_for_token(_qp["code"], _redirect_uri)
        st.query_params.clear()
        st.success("เชื่อมต่อ Gmail สำเร็จ — ไปที่เมนู 'TOR จากอีเมล' ได้เลย")
    except Exception as e:
        st.query_params.clear()
        st.error(f"เชื่อมต่อ Gmail ไม่สำเร็จ: {e}")

''' + anchor

    content = content.replace(anchor, insertion, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ app.py: เพิ่มการประมวลผล Gmail OAuth callback ก่อน require_login() แล้ว")

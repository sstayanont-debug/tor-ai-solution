"""
gmail_web_oauth_fix2.py — ส่วนที่เหลือจากรอบแรก (ที่ข้ามไปเพราะข้อความไม่ตรงเป๊ะ)
1) เพิ่มฟังก์ชัน get_gmail_token/set_gmail_token/clear_gmail_token ต่อท้าย db.py
2) แทนที่ส่วน "การเชื่อมต่อ Gmail" ในหน้า pages/8_TOR_จากอีเมล.py โดยอ้างอิงจากเลขบรรทัด (บรรทัด 29-52)
   แทนการจับคู่ข้อความเป๊ะๆ เพื่อเลี่ยงปัญหาอีโมจิไม่ตรงกัน

รันครั้งเดียวที่โฟลเดอร์ tor-ai-solution: python3 gmail_web_oauth_fix2.py
"""

# ---------------------------------------------------------------------------
# 1) db.py — เพิ่มฟังก์ชัน gmail token (ต่อท้ายไฟล์ ปลอดภัยสุด ไม่ต้องจับคู่ข้อความ)
# ---------------------------------------------------------------------------
with open("db.py", "r", encoding="utf-8") as f:
    db_content = f.read()

if "def get_gmail_token" in db_content:
    print("db.py: มีฟังก์ชัน get_gmail_token อยู่แล้ว ข้ามการเพิ่มซ้ำ")
else:
    db_content += '''

# -------------------- Gmail OAuth token (Inbox TOR Watcher) --------------------

def get_gmail_token() -> str:
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
'''
    with open("db.py", "w", encoding="utf-8") as f:
        f.write(db_content)
    print("✅ db.py: เพิ่มฟังก์ชัน get_gmail_token / set_gmail_token / clear_gmail_token ต่อท้ายไฟล์แล้ว")


# ---------------------------------------------------------------------------
# 2) pages/8_TOR_จากอีเมล.py — แทนที่บรรทัด 29-52 (ส่วนเชื่อมต่อ Gmail) ด้วยเลขบรรทัด
# ---------------------------------------------------------------------------
page8_path = "pages/8_TOR_จากอีเมล.py"
with open(page8_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

marker_line = None
for i, line in enumerate(lines):
    if "การเชื่อมต่อ Gmail" in line and line.strip().startswith("#"):
        marker_line = i
        break

if marker_line is None:
    print("⚠️  pages/8: ไม่พบบรรทัด comment 'การเชื่อมต่อ Gmail' — อาจแก้ไปแล้ว หรือโครงสร้างเปลี่ยน กรุณาแจ้งเพื่อตรวจสอบ")
else:
    # หาบรรทัด st.stop() ถัดไปหลัง marker (ปิดท้ายบล็อกเดิม)
    end_line = None
    for j in range(marker_line, len(lines)):
        if lines[j].strip() == "st.stop()" and "is_connected" in lines[j - 1]:
            end_line = j
            break

    if end_line is None:
        print("⚠️  pages/8: หาจุดจบของบล็อกเดิมไม่เจอ กรุณาแจ้งเพื่อตรวจสอบ")
    else:
        new_block = '''# ------------------- การเชื่อมต่อ Gmail (Web OAuth — ใช้ได้ทั้งบนเครื่องและบนคลาวด์) -------------------
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
        st.success("เชื่อมต่อ Gmail แล้ว")
    else:
        st.info("ยังไม่ได้เชื่อมต่อ Gmail — กดปุ่มเชื่อมต่อ จะเปิดแท็บใหม่ให้ล็อกอิน Gmail แล้วกลับมาหน้านี้อัตโนมัติ")
with col2:
    if email_watcher.is_connected():
        if st.button("ยกเลิกการเชื่อมต่อ"):
            email_watcher.disconnect()
            st.rerun()
    else:
        try:
            auth_url, _state = email_watcher.get_authorization_url(REDIRECT_URI)
            st.link_button("เชื่อมต่อ Gmail", auth_url, type="primary")
        except Exception as e:
            st.error(f"ตั้งค่าไม่ครบ: {e}")

if not email_watcher.is_connected():
    st.stop()
'''
        new_lines = lines[:marker_line] + [new_block] + lines[end_line + 1:]
        with open(page8_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        print(f"✅ pages/8: แทนที่บรรทัด {marker_line + 1}-{end_line + 1} ด้วยโค้ด Web OAuth ใหม่แล้ว")

print("\n=== เสร็จสิ้น ===")

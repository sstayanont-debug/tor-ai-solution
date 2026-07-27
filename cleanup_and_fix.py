import db, re

# ลบ RFQ ซ้ำ เก็บไว้แค่ id=2
with db.get_conn() as conn:
    conn.execute("DELETE FROM rfq_items WHERE rfq_id IN (1,3,4)")
    conn.execute("DELETE FROM rfqs WHERE id IN (1,3,4)")
print("ลบ RFQ ซ้ำเรียบร้อย เหลือแค่ id=2")

# แก้โค้ดไม่ให้ dropdown ชื่อชนกันอีก
path = "pages/5_จัดซื้อRFQ.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = '''rfq_map = {f"{r['title']} ({r['status']})": r["id"] for r in rfqs}'''
new = '''rfq_map = {f"{r['title']} ({r['status']}) #{r['id']}": r["id"] for r in rfqs}'''

if old in content:
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("แก้โค้ด dropdown เรียบร้อย")
else:
    print("ไม่พบบรรทัดที่ต้องแก้ (อาจแก้ไปแล้ว)")

import db
with db.get_conn() as conn:
    conn.execute("UPDATE bom_items SET category='hardware' WHERE category='Hardware'")
    conn.execute("UPDATE bom_items SET category='software' WHERE category='Software'")
print("แก้ไขเรียบร้อย")

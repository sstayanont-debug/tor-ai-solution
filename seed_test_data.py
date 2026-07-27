import db

db.init_db()

project_id = db.create_project(
    name="โครงการทดสอบ RFQ",
    tor_text="ข้อความ TOR ทดสอบ สำหรับทดสอบระบบจัดซื้อและสัญญา",
)
db.update_project(project_id, status="won")

bom_id = db.create_bom(project_id, solution_architecture_summary="ระบบทดสอบ", notes="สร้างโดยสคริปต์ทดสอบ")
db.add_bom_items(bom_id, [
    {"category": "Hardware", "item_name": "เครื่องคอมพิวเตอร์ตั้งโต๊ะ", "spec": "Core i5, RAM 16GB", "qty": 10, "unit": "เครื่อง", "unit_cost": 15000, "unit_price": 18000, "source": "manual_test"},
    {"category": "Software", "item_name": "License Windows 11 Pro", "spec": "OEM", "qty": 10, "unit": "license", "unit_cost": 4500, "unit_price": 5500, "source": "manual_test"},
])

print(f"สร้างโครงการทดสอบสำเร็จ! project_id={project_id}, bom_id={bom_id}, สถานะ=won")

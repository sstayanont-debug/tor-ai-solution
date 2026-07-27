import db
rfqs = db.get_rfqs_for_project(1)
for r in rfqs:
    items = db.get_rfq_items(r["id"])
    print(f"RFQ id={r['id']} title={r['title']} status={r['status']} จำนวนรายการ={len(items)}")

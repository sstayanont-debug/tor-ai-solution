"""
egp_intelligence.py — e-GP Market Intelligence

ดึงข้อมูล "สัญญาจัดซื้อจัดจ้างภาครัฐที่ประมูลเสร็จแล้ว" จาก Open Data ทางการของกรมบัญชีกลาง
(govspending.data.go.th, บริการ CGDContract) มาใช้วิเคราะห์คู่แข่ง/เบนช์มาร์กราคาก่อนเข้าประมูลงานใหม่

**นี่ไม่ใช่การ scrape เว็บ e-GP** — เป็น REST API เปิดเผยอย่างเป็นทางการที่รัฐจัดทำไว้ให้ใช้งานได้เลย
แต่ข้อมูลที่ได้คือสัญญาที่ประมูล "เสร็จแล้ว" เท่านั้น (ไม่มี live feed ของประกาศที่เปิดรับอยู่ตอนนี้)

ต้องขอ API key ฟรีที่ https://opend.data.go.th/register_api ก่อน แล้วตั้งค่าในไฟล์ .env (EGP_API_KEY)

**อัปเดต:** ยืนยัน schema จริงจากเอกสารทางการแล้ว (govspendingbeta.data.go.th/api/documentation) —
- `year` เป็นพารามิเตอร์บังคับ (required) ถ้าไม่ระบุ ระบบจะ default เป็นปีงบประมาณ พ.ศ. ปัจจุบันให้อัตโนมัติ
- field ราคาระดับบนสุดที่ยืนยันได้คือ sum_price_agree / project_money / price_build
- field ชื่อผู้ชนะ (winner) และ price_agree ต่อสัญญา อยู่ซ้อนอยู่ใน record["contract"][0] ไม่ใช่ระดับบนสุด
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://opend.data.go.th/govspending/cgdcontract"

WINNER_FIELD_CANDIDATES = ["winner_name", "winner", "winner_tin_name", "company_name", "vendor_name"]
PRICE_FIELD_CANDIDATES = ["sum_price_agree", "project_money", "price_build", "price_agree", "contract_price", "price", "budget"]
DATE_FIELD_CANDIDATES = ["announce_date", "contract_date", "sign_date", "date"]


def current_thai_year() -> str:
    """ปี พ.ศ. ปัจจุบัน — ใช้เป็นค่า default ของ year เพราะเป็นพารามิเตอร์บังคับของ API นี้"""
    return str(datetime.now().year + 543)


def is_configured() -> bool:
    return bool(os.environ.get("EGP_API_KEY"))


def _pick_field(record: dict, candidates: list, default=""):
    for c in candidates:
        v = record.get(c)
        if v not in (None, ""):
            return v
    return default


def _pick_from_contract(record: dict, field_candidates: list, default=""):
    """ดึงค่าจาก record['contract'][0] (ซ้อนอยู่ใน array) — ใช้กับ winner/price_agree"""
    contracts = record.get("contract")
    if isinstance(contracts, list) and contracts:
        first = contracts[0]
        if isinstance(first, dict):
            return _pick_field(first, field_candidates, default)
    return default


def search_contracts(keyword: str = "", dept_code: str = "", winner_tin: str = "",
                      year: str = "", budget_start: str = "", budget_end: str = "",
                      offset: int = 0, limit_display: int = 50) -> dict:
    """ค้นหาสัญญาที่ประมูลเสร็จแล้ว คืนค่า {total_project, total_price, records: [...], raw}"""
    api_key = os.environ.get("EGP_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ไม่พบ EGP_API_KEY กรุณาขอ API key ฟรีที่ https://opend.data.go.th/register_api "
            "แล้วตั้งค่าในไฟล์ .env"
        )

    # year เป็นพารามิเตอร์บังคับของ API นี้ — ถ้าผู้ใช้ไม่กรอก ให้ default เป็นปีปัจจุบัน
    year = year.strip() if year else ""
    if not year:
        year = current_thai_year()

    params = {"offset": offset, "year": year}
    if keyword:
        params["keyword"] = keyword
    if dept_code:
        params["dept_code"] = dept_code
    if winner_tin:
        params["winner_tin"] = winner_tin
    if budget_start:
        params["budget_start"] = budget_start
    if budget_end:
        params["budget_end"] = budget_end

    # หมายเหตุ: พอร์ทัล data.go.th/opend.data.go.th ยืนยัน token ผ่าน HTTP header
    # "api-key" ไม่ใช่ query string parameter (สาเหตุที่แท้จริงของ 404 ที่เจอก่อนหน้านี้
    # แม้จะใส่ year ครบแล้วก็ตาม) — ส่งทั้ง header และ query param ไว้กันเหนียว
    # เผื่อ gateway ฝั่งนี้อ่านจากจุดใดจุดหนึ่ง
    headers = {"api-key": api_key}
    params["api-key"] = api_key

    resp = requests.get(API_URL, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    status = data.get("status")
    if status is False or str(status).lower() in ("false", "0"):
        raise RuntimeError(f"e-GP API ตอบกลับข้อผิดพลาด: {data.get('msg', 'ไม่ทราบสาเหตุ')}")

    records = data.get("result")
    if records is None:
        records = data.get("data", [])
    if isinstance(records, dict):
        records = records.get("data") or records.get("list") or []
    if not isinstance(records, list):
        records = []

    normalized = []
    for r in records[:limit_display]:
        if not isinstance(r, dict):
            continue
        winner = _pick_from_contract(r, WINNER_FIELD_CANDIDATES) or _pick_field(r, WINNER_FIELD_CANDIDATES)
        price = _pick_field(r, PRICE_FIELD_CANDIDATES) or _pick_from_contract(r, ["price_agree"])
        normalized.append({
            "project_name": r.get("project_name", ""),
            "dept_name": r.get("dept_name", "") or r.get("dept_sub_name", ""),
            "project_type_name": r.get("project_type_name", ""),
            "purchase_method_name": r.get("purchase_method_name", ""),
            "announce_date": _pick_field(r, DATE_FIELD_CANDIDATES),
            "winner": winner,
            "price": price,
            "raw": r,
        })

    summary = data.get("summary", {}) or {}
    return {
        "total_project": summary.get("total_project", len(normalized)),
        "total_price": summary.get("total_price", ""),
        "year_used": year,
        "records": normalized,
        "raw_response": data,
    }


def summarize_for_competitor(search_result: dict) -> str:
    """สรุปผลการค้นหาเป็นข้อความ ให้ AI (analyze_competitor) ใช้วิเคราะห์ต่อได้"""
    records = search_result.get("records", [])
    lines = [
        f"จำนวนโครงการที่พบจากข้อมูล e-GP (govspending.data.go.th) ปีงบประมาณ {search_result.get('year_used', '-')}: "
        f"{search_result.get('total_project', len(records))}",
    ]
    if search_result.get("total_price"):
        lines.append(f"มูลค่ารวม: {search_result['total_price']}")
    for r in records[:15]:
        lines.append(
            f"- {r['project_name']} | หน่วยงาน: {r['dept_name']} | ผู้ชนะ: {r['winner'] or '-'} | "
            f"ราคา: {r['price'] or '-'} | วันที่: {r['announce_date'] or '-'}"
        )
    return "\n".join(lines)

"""
ai_engine.py — เรียก Claude API เพื่อวิเคราะห์ TOR, ประเมินความเสี่ยง,
ประเมินโอกาสชนะงาน, สร้างเนื้อหาสนับสนุนการขาย และแตก milestone สัญญา

ใช้ Claude tool-use (forced tool_choice) เพื่อบังคับให้ผลลัพธ์เป็น JSON
ที่มีโครงสร้างแน่นอน ลดปัญหาการ parse ข้อความอิสระ
"""

import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.environ.get("TOR_AI_MODEL", "claude-sonnet-5")


def get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ไม่พบ ANTHROPIC_API_KEY กรุณาตั้งค่าใน environment variable หรือไฟล์ .env "
            "(ดูวิธีตั้งค่าใน README.md)"
        )
    return anthropic.Anthropic(api_key=api_key)


def _call_tool(system_prompt: str, user_prompt: str, tool_name: str, tool_description: str,
                input_schema: dict, model: str = None, max_tokens: int = 4096) -> dict:
    client = get_client()
    resp = client.messages.create(
        model=model or DEFAULT_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        tools=[{
            "name": tool_name,
            "description": tool_description,
            "input_schema": input_schema,
        }],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user_prompt}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    raise RuntimeError(f"AI ไม่ได้ส่งผลลัพธ์กลับมาในรูปแบบที่กำหนด (tool: {tool_name}) กรุณาลองใหม่อีกครั้ง")
    raise RuntimeError("Claude ไม่ได้ตอบกลับด้วย tool_use ตามที่คาดไว้")


# ---------------------------------------------------------------------------
# 1) วิเคราะห์ TOR
# ---------------------------------------------------------------------------

TOR_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {"type": "string"},
        "agency_or_client": {"type": "string"},
        "budget_estimate_thb": {"type": "string"},
        "submission_deadline": {"type": "string"},
        "project_duration": {"type": "string"},
        "scope_summary": {"type": "string", "description": "สรุปขอบเขตงานแบบกระชับ 3-6 ประโยค"},
        "qualification_requirements": {
            "type": "array", "items": {"type": "string"},
            "description": "คุณสมบัติผู้ยื่นข้อเสนอที่กำหนดใน TOR"
        },
        "evaluation_criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "weight_percent": {"type": "string"}
                },
                "required": ["criterion"]
            },
            "description": "เกณฑ์การให้คะแนน/ตัดสินและน้ำหนักคะแนน (ถ้าระบุ)"
        },
        "mandatory_documents": {"type": "array", "items": {"type": "string"}},
        "key_risks": {"type": "array", "items": {"type": "string"}, "description": "ความเสี่ยงหรือเงื่อนไขที่ควรระวังจากตัว TOR"},
        "penalty_clauses": {"type": "string", "description": "เงื่อนไขค่าปรับ/บทลงโทษที่ระบุใน TOR ถ้ามี"},
        "notes": {"type": "string", "description": "ข้อสังเกตอื่นๆ ที่เป็นประโยชน์"}
    },
    "required": ["project_name", "scope_summary", "qualification_requirements", "key_risks"]
}


def analyze_tor(tor_text: str) -> dict:
    system_prompt = (
        "คุณเป็นที่ปรึกษาผู้เชี่ยวชาญด้านการวิเคราะห์เอกสาร TOR (Terms of Reference) "
        "สำหรับงานประมูลโครงการภาครัฐและเอกชนในประเทศไทย มีหน้าที่สกัดข้อมูลสำคัญจากเอกสาร TOR "
        "อย่างแม่นยำ ครบถ้วน และเป็นกลาง หากข้อมูลใดไม่ปรากฏใน TOR ให้ระบุว่า 'ไม่ระบุ'"
    )
    user_prompt = f"นี่คือเนื้อหา TOR ที่ต้องวิเคราะห์:\n\n---\n{tor_text}\n---\n\nกรุณาสกัดข้อมูลตามโครงสร้างที่กำหนด"
    return _call_tool(
        system_prompt, user_prompt,
        tool_name="extract_tor_analysis",
        tool_description="บันทึกผลการวิเคราะห์ TOR แบบมีโครงสร้าง",
        input_schema=TOR_ANALYSIS_SCHEMA,
    )


# ---------------------------------------------------------------------------
# 2) ประเมินความเสี่ยง
# ---------------------------------------------------------------------------

RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "financial_risk": {"type": "object", "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5}, "reason": {"type": "string"}}},
        "technical_risk": {"type": "object", "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5}, "reason": {"type": "string"}}},
        "timeline_risk": {"type": "object", "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5}, "reason": {"type": "string"}}},
        "competition_risk": {"type": "object", "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5}, "reason": {"type": "string"}}},
        "legal_compliance_risk": {"type": "object", "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 5}, "reason": {"type": "string"}}},
        "overall_risk_score": {"type": "number", "description": "ค่าเฉลี่ยความเสี่ยงรวม 1-5"},
        "overall_risk_level": {"type": "string", "enum": ["ต่ำ", "ปานกลาง", "สูง", "สูงมาก"]},
        "risk_narrative": {"type": "string", "description": "สรุปภาพรวมความเสี่ยง 3-5 ประโยค"},
        "mitigation_suggestions": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["financial_risk", "technical_risk", "timeline_risk", "competition_risk",
                 "legal_compliance_risk", "overall_risk_score", "overall_risk_level", "risk_narrative"]
}


def assess_risk(tor_analysis: dict, company_profile: dict) -> dict:
    system_prompt = (
        "คุณเป็นผู้เชี่ยวชาญบริหารความเสี่ยงโครงการประมูลงาน ให้คะแนนความเสี่ยง 1 (ต่ำมาก) ถึง 5 (สูงมาก) "
        "ในแต่ละมิติ โดยพิจารณาทั้งเงื่อนไขจาก TOR และศักยภาพของบริษัทที่จะเข้าประมูล "
        "ให้เหตุผลประกอบทุกคะแนนอย่างกระชับและอิงข้อเท็จจริง"
    )
    user_prompt = (
        f"ผลวิเคราะห์ TOR:\n{tor_analysis}\n\n"
        f"โปรไฟล์บริษัทผู้ประมูล:\n{company_profile}\n\n"
        "กรุณาประเมินความเสี่ยงตามโครงสร้างที่กำหนด"
    )
    return _call_tool(
        system_prompt, user_prompt,
        tool_name="assess_risk",
        tool_description="บันทึกผลการประเมินความเสี่ยงแบบมีโครงสร้าง",
        input_schema=RISK_SCHEMA,
    )


# ---------------------------------------------------------------------------
# 3) ประเมินโอกาสชนะงาน
# ---------------------------------------------------------------------------

WIN_PROB_SCHEMA = {
    "type": "object",
    "properties": {
        "win_probability_percent": {"type": "number", "minimum": 0, "maximum": 100},
        "recommendation": {"type": "string", "enum": ["ควรเข้าประมูล", "ควรพิจารณาอย่างระมัดระวัง", "ไม่ควรเข้าประมูล"]},
        "key_strengths": {"type": "array", "items": {"type": "string"}},
        "key_weaknesses": {"type": "array", "items": {"type": "string"}},
        "competitive_positioning": {"type": "string", "description": "การวางตำแหน่งเทียบคู่แข่งที่คาดว่าจะเข้าประมูล"},
        "reasoning": {"type": "string", "description": "เหตุผลสนับสนุนตัวเลข % โดยละเอียด"}
    },
    "required": ["win_probability_percent", "recommendation", "key_strengths", "key_weaknesses", "reasoning"]
}


def estimate_win_probability(tor_analysis: dict, risk_assessment: dict, company_profile: dict) -> dict:
    system_prompt = (
        "คุณเป็นที่ปรึกษากลยุทธ์การประมูลงานที่มีประสบการณ์สูง หน้าที่ของคุณคือประเมินโอกาสชนะงาน (win probability) "
        "เป็นเปอร์เซ็นต์ โดยพิจารณาความสอดคล้องระหว่างศักยภาพบริษัทกับข้อกำหนด TOR ระดับความเสี่ยง "
        "และภาพรวมการแข่งขัน ให้ตัวเลขที่สมเหตุสมผลและอธิบายเหตุผลอย่างตรงไปตรงมา ไม่มองโลกในแง่ดีเกินจริง"
    )
    user_prompt = (
        f"ผลวิเคราะห์ TOR:\n{tor_analysis}\n\n"
        f"ผลประเมินความเสี่ยง:\n{risk_assessment}\n\n"
        f"โปรไฟล์บริษัทผู้ประมูล:\n{company_profile}\n\n"
        "กรุณาประเมินโอกาสชนะงานตามโครงสร้างที่กำหนด"
    )
    return _call_tool(
        system_prompt, user_prompt,
        tool_name="estimate_win_probability",
        tool_description="บันทึกผลประเมินโอกาสชนะงานแบบมีโครงสร้าง",
        input_schema=WIN_PROB_SCHEMA,
    )


# ---------------------------------------------------------------------------
# 4) เนื้อหาสนับสนุนการขาย
# ---------------------------------------------------------------------------

SALES_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string", "description": "บทสรุปผู้บริหารสำหรับข้อเสนอ 4-8 ประโยค"},
        "value_proposition": {"type": "string"},
        "key_differentiators": {"type": "array", "items": {"type": "string"}},
        "key_messages": {"type": "array", "items": {"type": "string"}, "description": "key message สำหรับทีมขายใช้พูดคุยกับลูกค้า/กรรมการ"},
        "objection_handling": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "objection": {"type": "string"}, "response": {"type": "string"}}}
        },
        "pricing_strategy_notes": {"type": "string"}
    },
    "required": ["executive_summary", "value_proposition", "key_differentiators", "key_messages"]
}


def generate_sales_support(tor_analysis: dict, win_probability: dict, company_profile: dict) -> dict:
    system_prompt = (
        "คุณเป็นผู้เชี่ยวชาญด้านการเขียนข้อเสนอโครงการ (proposal writing) และกลยุทธ์การขาย B2B/B2G "
        "สร้างเนื้อหาที่ทีมขายนำไปใช้ประกอบการยื่นข้อเสนอและนำเสนอต่อคณะกรรมการได้ทันที "
        "เน้นความน่าเชื่อถือ ตรงประเด็นกับ TOR และสอดคล้องกับจุดแข็งของบริษัท"
    )
    user_prompt = (
        f"ผลวิเคราะห์ TOR:\n{tor_analysis}\n\n"
        f"ผลประเมินโอกาสชนะงาน:\n{win_probability}\n\n"
        f"โปรไฟล์บริษัท:\n{company_profile}\n\n"
        "กรุณาสร้างเนื้อหาสนับสนุนการขายตามโครงสร้างที่กำหนด"
    )
    return _call_tool(
        system_prompt, user_prompt,
        tool_name="generate_sales_support",
        tool_description="บันทึกเนื้อหาสนับสนุนการขายแบบมีโครงสร้าง",
        input_schema=SALES_SCHEMA,
    )


# ---------------------------------------------------------------------------
# 5) แตก milestone สัญญา (ใช้ตอนได้งานแล้ว)
# ---------------------------------------------------------------------------

MILESTONES_SCHEMA = {
    "type": "object",
    "properties": {
        "milestones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due_date_or_offset": {"type": "string", "description": "วันครบกำหนด หรือระยะเวลานับจากวันเริ่มสัญญา เช่น 'วันที่ 30 หลังลงนาม'"},
                    "deliverable": {"type": "string"},
                    "payment_percent": {"type": "string", "description": "สัดส่วนการเบิกจ่ายที่ผูกกับ milestone นี้ (ถ้ามี)"},
                    "notes": {"type": "string"}
                },
                "required": ["title", "deliverable"]
            }
        }
    },
    "required": ["milestones"]
}


BOM_SCHEMA = {
    "type": "object",
    "properties": {
        "solution_architecture_summary": {"type": "string", "description": "ร่างโครงสร้างวิธีแก้ไขปัญหา (solution architecture) ตอบโจทย์ TOR แบบสั้นกระชับ"},
        "target_margin_percent": {"type": "number", "description": "% กำไรเป้าหมายที่แนะนำ พิจารณาจากความเสี่ยงและการแข่งขัน"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["hardware", "software", "labor", "subcontract", "license", "other"]},
                    "item_name": {"type": "string"},
                    "spec": {"type": "string"},
                    "qty": {"type": "number"},
                    "unit": {"type": "string"},
                    "unit_cost": {"type": "number", "description": "ต้นทุนประเมินต่อหน่วย (บาท) ประเมินตามราคาตลาดทั่วไปถ้าไม่มีข้อมูลบริษัท"},
                    "unit_price": {"type": "number", "description": "ราคาขายต่อหน่วยที่แนะนำ (บาท) รวม margin เป้าหมายแล้ว"},
                },
                "required": ["category", "item_name", "qty", "unit"]
            }
        }
    },
    "required": ["solution_architecture_summary", "items"]
}


def generate_bom_costing(tor_analysis: dict, company_profile: dict) -> dict:
    system_prompt = (
        "คุณเป็นวิศวกรโซลูชัน (solution architect) และผู้เชี่ยวชาญด้านการตั้งราคาโครงการ B2B "
        "หน้าที่คือร่างโครงสร้างวิธีแก้ไขปัญหาตามขอบเขตงานใน TOR แล้วแตกเป็นรายการ BOM "
        "(hardware/software/labor/subcontract/license) พร้อมประเมินต้นทุนและราคาขายต่อหน่วยอย่างสมเหตุสมผล "
        "ตามราคาตลาดทั่วไปในประเทศไทย ถ้าไม่มีข้อมูลราคาที่แน่นอน ให้ประเมินแบบระมัดระวังและระบุว่าเป็นค่าประเมิน"
    )
    user_prompt = (
        f"ผลวิเคราะห์ TOR:\n{tor_analysis}\n\n"
        f"โปรไฟล์บริษัท (ความเชี่ยวชาญ/ทรัพยากรที่มี):\n{company_profile}\n\n"
        "กรุณาร่าง solution architecture และ BOM ตามโครงสร้างที่กำหนด"
    )
    return _call_tool(
        system_prompt, user_prompt,
        tool_name="generate_bom_costing",
        tool_description="บันทึกโครงสร้างวิธีแก้ไขปัญหาและ BOM แบบมีโครงสร้าง",
        input_schema=BOM_SCHEMA,
    )


COMPETITOR_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "differentiator_suggestions": {"type": "string", "description": "จุดข่มที่ควรเน้นในเล่มข้อเสนอราคา เทียบกับคู่แข่งรายนี้"},
        "risk_notes": {"type": "string", "description": "ข้อสังเกตความเสี่ยงจากการแข่งขันกับคู่แข่งรายนี้"}
    },
    "required": ["differentiator_suggestions"]
}


def analyze_competitor(tor_analysis: dict, company_profile: dict, competitor_info: str) -> dict:
    system_prompt = (
        "คุณเป็นที่ปรึกษากลยุทธ์การแข่งขันด้านการประมูลงาน วิเคราะห์ข้อมูลคู่แข่งที่ผู้ใช้ให้มา "
        "เทียบกับจุดแข็งของบริษัทเราและข้อกำหนดใน TOR แล้วแนะนำจุดข่ม (differentiator) ที่ควรเขียนเน้นในข้อเสนอ "
        "เพื่อสร้างความได้เปรียบเทียบคู่แข่งรายนี้โดยเฉพาะ"
    )
    user_prompt = (
        f"ผลวิเคราะห์ TOR:\n{tor_analysis}\n\n"
        f"โปรไฟล์บริษัทเรา:\n{company_profile}\n\n"
        f"ข้อมูลคู่แข่งที่ทราบ:\n{competitor_info}\n\n"
        "กรุณาวิเคราะห์ตามโครงสร้างที่กำหนด"
    )
    return _call_tool(
        system_prompt, user_prompt,
        tool_name="analyze_competitor",
        tool_description="บันทึกผลวิเคราะห์คู่แข่งแบบมีโครงสร้าง",
        input_schema=COMPETITOR_ANALYSIS_SCHEMA,
    )


QUOTE_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string"},
        "total_price": {"type": "number"},
        "delivery_days": {"type": "integer"},
        "sla_terms": {"type": "string"},
        "warranty": {"type": "string"},
        "spec_match_percent": {"type": "number", "minimum": 0, "maximum": 100, "description": "% ความตรงของสเปคที่เสนอเทียบกับรายการที่ขอ (RFQ items)"},
        "spec_match_notes": {"type": "string"},
        "sla_delay_risk": {"type": "string", "enum": ["ต่ำ", "ปานกลาง", "สูง"], "description": "ความเสี่ยงที่ vendor จะส่งมอบล่าช้าตามเงื่อนไข SLA/ประวัติที่ระบุในใบเสนอราคา"},
        "sla_risk_reason": {"type": "string"},
    },
    "required": ["total_price", "spec_match_percent"]
}


def extract_quote_data(rfq_items: list, raw_quote_text: str) -> dict:
    system_prompt = (
        "คุณเป็นผู้เชี่ยวชาญงานจัดซื้อ (procurement) หน้าที่คือสกัดข้อมูลสำคัญจากใบเสนอราคาของ vendor "
        "ได้แก่ ราคารวม ระยะเวลาส่งมอบ เงื่อนไข SLA/ประกัน แล้วประเมินว่าสเปคที่เสนอตรงกับรายการที่ขอกี่เปอร์เซ็นต์ "
        "และประเมินความเสี่ยงที่จะส่งมอบล่าช้าจากเงื่อนไขที่ระบุในใบเสนอราคา"
    )
    user_prompt = (
        f"รายการที่ขอราคา (RFQ items):\n{rfq_items}\n\n"
        f"เนื้อหาใบเสนอราคาจาก vendor:\n{raw_quote_text}\n\n"
        "กรุณาสกัดข้อมูลตามโครงสร้างที่กำหนด"
    )
    return _call_tool(
        system_prompt, user_prompt,
        tool_name="extract_quote_data",
        tool_description="บันทึกข้อมูลที่สกัดจากใบเสนอราคาแบบมีโครงสร้าง",
        input_schema=QUOTE_EXTRACTION_SCHEMA,
    )


REDLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_risk_summary": {"type": "string", "description": "สรุปภาพรวมความเสี่ยงของร่างสัญญาฉบับนี้"},
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_excerpt": {"type": "string", "description": "ข้อความที่ตัดมาจากสัญญา (ย่อพอสังเขป)"},
                    "risk_level": {"type": "string", "enum": ["ต่ำ", "ปานกลาง", "สูง"]},
                    "issue": {"type": "string", "description": "ปัญหา/ความเสี่ยงของข้อนี้ เช่น ค่าปรับเกินมาตรฐาน, เงื่อนไข IP ไม่เป็นธรรม"},
                    "counter_proposal": {"type": "string", "description": "ข้อเสนอแย้งที่แนะนำให้เจรจากับคู่ค้า"}
                },
                "required": ["clause_excerpt", "risk_level", "issue"]
            }
        }
    },
    "required": ["overall_risk_summary", "clauses"]
}


def redline_contract(contract_text: str, company_profile: dict) -> dict:
    system_prompt = (
        "คุณเป็นที่ปรึกษากฎหมายสัญญาโครงการ B2B/B2G ที่เชี่ยวชาญด้านการ redline ร่างสัญญา "
        "หน้าที่คือสแกนร่างสัญญาทั้งฉบับ หาข้อที่เสี่ยงหรือเสียเปรียบฝ่ายเรา เช่น เงื่อนไขค่าปรับเกินมาตรฐาน "
        "ข้อตกลงทรัพย์สินทางปัญญา (IP) ที่ไม่เป็นธรรม เงื่อนไขงวดชำระเงินที่ผิดปกติ ข้อผูกมัดที่คลุมเครือ "
        "ให้ระบุ risk_level และข้อเสนอแย้งที่เจรจาได้จริงในบริบทกฎหมายไทย นี่ไม่ใช่คำแนะนำทางกฎหมายที่สมบูรณ์ "
        "แต่เป็นการช่วยคัดกรองเบื้องต้นก่อนส่งฝ่ายกฎหมายตรวจสอบจริง"
    )
    user_prompt = (
        f"ร่างสัญญา:\n{contract_text[:15000]}\n\n"
        f"โปรไฟล์บริษัทเรา (ฝ่ายที่ต้องพิจารณาความเสี่ยง):\n{company_profile}\n\n"
        "กรุณา redline สัญญาตามโครงสร้างที่กำหนด"
    )
    return _call_tool(
        system_prompt, user_prompt,
        tool_name="redline_contract",
        tool_description="บันทึกผลการ redline สัญญาแบบมีโครงสร้าง",
        input_schema=REDLINE_SCHEMA,
        max_tokens=8192,
    )


OBLIGATIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "obligations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "obligation_text": {"type": "string"},
                    "category": {"type": "string", "enum": ["deliverable", "payment", "reporting", "insurance", "legal", "other"]},
                    "responsible_party": {"type": "string", "enum": ["ผู้รับจ้าง", "ผู้ว่าจ้าง"]},
                    "due_date_or_trigger": {"type": "string"},
                    "penalty_if_missed": {"type": "string"}
                },
                "required": ["obligation_text", "category", "responsible_party"]
            }
        }
    },
    "required": ["obligations"]
}


def extract_obligations(contract_text: str) -> dict:
    system_prompt = (
        "คุณเป็นผู้จัดการโครงการที่เชี่ยวชาญการบริหารสัญญา หน้าที่คือดึงข้อผูกมัด (obligations) ทั้งหมดจากสัญญา "
        "ไม่ใช่แค่ deliverable แต่รวมถึงการรายงาน การประกันภัย เงื่อนไขทางกฎหมาย และกำหนดการชำระเงิน "
        "ระบุฝ่ายที่รับผิดชอบ กำหนดเวลา/เงื่อนไขทริกเกอร์ และบทลงโทษถ้าไม่ทำตาม (ถ้าระบุในสัญญา)"
    )
    user_prompt = f"เนื้อหาสัญญา:\n{contract_text[:15000]}\n\nกรุณาดึงข้อผูกมัดทั้งหมดตามโครงสร้างที่กำหนด"
    return _call_tool(
        system_prompt, user_prompt,
        tool_name="extract_obligations",
        tool_description="บันทึกรายการข้อผูกมัดของสัญญาแบบมีโครงสร้าง",
        input_schema=OBLIGATIONS_SCHEMA,
        max_tokens=8192,
    )


def extract_milestones(tor_analysis: dict, tor_text: str) -> dict:
    system_prompt = (
        "คุณเป็นผู้จัดการโครงการที่เชี่ยวชาญการบริหารสัญญา หน้าที่คือแตกงานจาก TOR ให้เป็น milestone/"
        "deliverable ที่ชัดเจน พร้อมกำหนดส่งงานและสัดส่วนการเบิกจ่ายเงิน (ถ้าระบุใน TOR) "
        "เพื่อใช้ติดตามความคืบหน้าสัญญาหลังจากได้งานแล้ว"
    )
    user_prompt = (
        f"ผลวิเคราะห์ TOR:\n{tor_analysis}\n\n"
        f"เนื้อหา TOR ต้นฉบับ (บางส่วน):\n{tor_text[:6000]}\n\n"
        "กรุณาแตก milestone ตามโครงสร้างที่กำหนด เรียงตามลำดับเวลา"
    )
    return _call_tool(
        system_prompt, user_prompt,
        tool_name="extract_milestones",
        tool_description="บันทึกรายการ milestone ของสัญญาแบบมีโครงสร้าง",
        input_schema=MILESTONES_SCHEMA,
    )


def extract_text_from_pdf_via_ai(pdf_bytes: bytes, max_pages_per_batch: int = 90) -> str:
    """อ่านข้อความจาก PDF ด้วย Claude โดยตรง (รองรับ PDF ที่สแกนมา/เป็นรูปภาพ ซึ่ง pypdf อ่านไม่ได้)
    ถ้าเอกสารมีหลายหน้าเกินขีดจำกัดต่อการเรียก จะแบ่งเป็นชุดๆ แล้วต่อข้อความกลับเป็นชิ้นเดียว"""
    import io
    import base64
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    client = get_client()

    all_text = []
    for start in range(0, total_pages, max_pages_per_batch):
        end = min(start + max_pages_per_batch, total_pages)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])
        buf = io.BytesIO()
        writer.write(buf)
        b64_data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")

        resp = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=8000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "กรุณาถอดข้อความทั้งหมดในเอกสาร PDF นี้ออกมาเป็นข้อความล้วน "
                            "ให้ครบทุกหน้าตามลำดับ ไม่ต้องสรุปหรือย่อ ไม่ต้องแสดงความเห็นเพิ่มเติม "
                            "ถ้าหน้าไหนมีตาราง ให้พยายามคงโครงสร้างข้อมูลไว้ในรูปแบบข้อความให้มากที่สุด"
                        ),
                    },
                ],
            }],
        )
        chunk_text = "".join(block.text for block in resp.content if block.type == "text")
        all_text.append(chunk_text)

    return "\n\n".join(all_text)

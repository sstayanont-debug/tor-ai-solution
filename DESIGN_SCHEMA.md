# End-to-End Enterprise Project Lifecycle Copilot — Database Schema & Workflow

เอกสารนี้ออกแบบสถาปัตยกรรมข้อมูลและ workflow สำหรับขยาย **TOR AI Solution** จากเครื่องมือวิเคราะห์ TOR
ให้ครอบคลุมวงจรโครงการ B2B ทั้งหมด: **งานขาย (Sales) → งานจัดซื้อ (Procurement) → งานสัญญา (Contract Lifecycle)**

หลักการออกแบบ: ทุกโครงการ (`projects`) เป็นศูนย์กลาง (hub) ที่โมดูลอื่นทั้งหมดเชื่อมเข้ามา
ทำให้ข้อมูลไหลต่อเนื่องกันตั้งแต่วันแรกที่เห็น TOR จนถึงวันปิดสัญญา ไม่ต้องย้ายข้อมูลข้ามระบบ

---

## 0. ภาพรวม Workflow ทั้งวงจร (Lifecycle)

```
┌─────────────┐   ┌──────────────┐   ┌────────────────┐   ┌──────────────┐   ┌───────────────┐
│  1. TOR      │──▶│ 2. Bid/No-Bid│──▶│ 3. Solution &   │──▶│ 4. Proposal & │──▶│ 5. ยื่นข้อเสนอ │
│  Analysis    │   │  Decision    │   │  Costing (BOM)  │   │ Competitor    │   │  (Submit)      │
│  (มีอยู่แล้ว)│   │  (มีอยู่แล้ว)│   │  (ใหม่)         │   │ Intel (ใหม่)  │   │                │
└─────────────┘   └──────────────┘   └────────────────┘   └──────────────┘   └───────┬───────┘
                                                                                        │
                        ┌───────────────────────────────────────────────────────────────┘
                        ▼
              ┌──────────────┐   ไม่ชนะ → ปิดสถานะ "lost" เก็บไว้เป็นฐานข้อมูลย้อนหลัง
              │  6. ผลประมูล  │
              └───────┬──────┘
                      │ ชนะงาน (won)
                      ▼
        ┌────────────────────┐   ┌──────────────────┐   ┌────────────────────┐
        │ 7. Contract         │──▶│ 8. Procurement /  │──▶│ 9. Milestone &      │
        │  Redlining (ใหม่)   │   │  RFQ/Vendor (ใหม่)│   │  Obligation Tracker │
        └────────────────────┘   └──────────────────┘   │  (มีอยู่แล้ว+ขยาย)  │
                                                          └────────────────────┘
```

**ขั้นตอนที่ 1-2 คือประตูตัดสินใจ (Gate)** — ระบบต้องวิเคราะห์ TOR และประเมิน Bid/No-Bid
**ก่อน** จะให้ทีมขายลงแรงทำ Solution/Costing/Proposal ต่อ เพื่อไม่ให้เสียเวลากับงานที่ไม่คุ้ม
(ส่วนนี้มีอยู่แล้วในแอปปัจจุบัน: `tor_analysis` → `risk_assessment` → `win_probability.recommendation`)

---

## 1. ตารางที่มีอยู่แล้ว (Existing)

| ตาราง | หน้าที่ |
|---|---|
| `company_profile` | โปรไฟล์บริษัทผู้ประมูล (ใช้เป็น context ให้ AI ทุกโมดูล) |
| `projects` | ศูนย์กลางของทุกโครงการ: `tor_text`, `tor_analysis`, `risk_assessment`, `win_probability`, `sales_support`, `status` |
| `milestones` | Milestone/deliverable ที่แตกจาก TOR หลังชนะงาน |

`projects.status` ปัจจุบัน: `analyzing → ready → submitted → won/lost → contract_active → contract_completed`

---

## 2. โมดูลงานขาย (Sales & Pipeline) — ตารางใหม่

### 2.1 `boms` + `bom_items` — Automated Solution Architecture & Costing

```sql
CREATE TABLE boms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    solution_architecture_summary TEXT,   -- AI ร่างโครงสร้างวิธีแก้ไขปัญหา
    total_cost_estimate REAL,             -- ต้นทุนรวมประเมิน
    total_price_estimate REAL,            -- ราคาขายรวมที่เสนอ
    target_margin_percent REAL,           -- % กำไรเป้าหมายที่ตั้งไว้
    actual_margin_percent REAL,           -- % กำไรจริงที่คำนวณได้จาก cost/price
    notes TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects (id)
);

CREATE TABLE bom_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bom_id INTEGER NOT NULL,
    category TEXT,          -- hardware / software / labor / subcontract / license / other
    item_name TEXT,
    spec TEXT,
    qty REAL,
    unit TEXT,
    unit_cost REAL,
    unit_price REAL,
    source TEXT,            -- 'company_catalog' | 'vendor_quote' | 'ai_estimate'
    FOREIGN KEY (bom_id) REFERENCES boms (id)
);
```

**Workflow:** อ่าน `tor_analysis.scope_summary` + `qualification_requirements` → AI ร่าง solution architecture
→ AI สร้างรายการ BOM เบื้องต้น (ประเมินราคาเองถ้ายังไม่มีฐานข้อมูลสินค้า) → ผู้ใช้ปรับ unit_cost/unit_price ในตาราง
→ ระบบคำนวณ margin อัตโนมัติ → ผลลัพธ์เชื่อมกลับไปใช้ใน `sales_support` (proposal) และเป็นต้นทาง RFQ ในขั้นจัดซื้อ

### 2.2 `competitors` — Competitor Bid Intelligence

```sql
CREATE TABLE competitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    competitor_name TEXT,
    past_win_rate TEXT,           -- ถ้ามีข้อมูลย้อนหลัง (เช่นจาก e-GP ที่ผู้ใช้ไปดึงมาวางเอง)
    estimated_bid_price TEXT,
    strengths TEXT,
    weaknesses TEXT,
    source TEXT,                  -- ผู้ใช้ระบุแหล่งข้อมูล เช่น 'e-GP', 'ประสบการณ์ตรง'
    ai_differentiator_suggestions TEXT,  -- AI แนะนำจุดข่มที่ควรเขียนในเล่มเสนอราคา
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects (id)
);
```

**Workflow:** ผู้ใช้กรอก/วางข้อมูลคู่แข่งที่ทราบ (คู่มือนี้ยังไม่รวมการดึงข้อมูล e-GP อัตโนมัติ — ต้องต่อ API/scraper
ภายนอกเพิ่มเติม ดู "ข้อจำกัดปัจจุบัน" ด้านล่าง) → AI วิเคราะห์เทียบกับจุดแข็งบริษัทเรา → เสนอ differentiator
ที่ควรใส่ใน `sales_support.key_differentiators`

---

## 3. โมดูลงานจัดซื้อ (Procurement) — ตารางใหม่

### 3.1 `vendors`

```sql
CREATE TABLE vendors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_name TEXT,
    category TEXT,          -- หมวดสินค้า/บริการที่ขาย
    contact_info TEXT,
    rating REAL,             -- คะแนนความน่าเชื่อถือสะสม (จากประวัติ SLA)
    notes TEXT,
    created_at TEXT
);
```

### 3.2 `rfqs` + `rfq_items` — สร้างจาก BOM ของโครงการที่ชนะ

```sql
CREATE TABLE rfqs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    bom_id INTEGER,               -- อ้างอิง BOM ต้นทาง (nullable — สร้างเองได้โดยไม่ผูก BOM)
    title TEXT,
    deadline TEXT,
    status TEXT DEFAULT 'draft',  -- draft / sent / comparing / awarded / closed
    created_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects (id),
    FOREIGN KEY (bom_id) REFERENCES boms (id)
);

CREATE TABLE rfq_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rfq_id INTEGER NOT NULL,
    item_name TEXT,
    spec TEXT,
    qty REAL,
    unit TEXT,
    FOREIGN KEY (rfq_id) REFERENCES rfqs (id)
);
```

### 3.3 `vendor_quotes` — Vendor Spec-Matching & RFQ Automation + SLA Risk

```sql
CREATE TABLE vendor_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rfq_id INTEGER NOT NULL,
    vendor_id INTEGER,
    vendor_name_freeform TEXT,     -- เผื่อยังไม่ได้บันทึกใน vendors master
    raw_quote_text TEXT,           -- เนื้อหาใบเสนอราคาต้นฉบับที่ผู้ใช้วาง/อัปโหลด
    ai_extracted JSON,             -- AI สกัด: total_price, delivery_days, spec_match_percent, sla_terms, warranty
    total_price REAL,
    delivery_days INTEGER,
    spec_match_percent REAL,       -- AI เทียบสเปคใน quote กับ rfq_items ว่าตรงกี่ %
    sla_delay_risk TEXT,           -- 'ต่ำ' | 'ปานกลาง' | 'สูง' — จาก Supplier SLA Predictor
    sla_risk_reason TEXT,
    status TEXT DEFAULT 'pending', -- pending / selected / rejected
    submitted_at TEXT,
    FOREIGN KEY (rfq_id) REFERENCES rfqs (id),
    FOREIGN KEY (vendor_id) REFERENCES vendors (id)
);
```

**Workflow:**
1. โครงการชนะงาน (`projects.status = won`) → สร้าง RFQ จากรายการ `bom_items` ที่เป็น category
   hardware/software/subcontract อัตโนมัติ
2. ผู้ใช้วาง/อัปโหลดใบเสนอราคาที่ได้รับจาก vendor แต่ละราย (ยังไม่มีระบบส่งอีเมลอัตโนมัติในเวอร์ชันนี้ —
   ต้องต่อ email/CRM connector เพิ่ม ดูข้อจำกัดด้านล่าง) → AI สกัดราคา/ระยะเวลาส่งมอบ/เงื่อนไข SLA
   ออกมาเป็นโครงสร้าง พร้อมประเมิน spec_match_percent เทียบกับ `rfq_items`
3. ระบบแสดง **Comparison Table** เทียบราคา/สเปค/delivery ของทุก vendor ในหน้าเดียว
4. AI ประเมินความเสี่ยงส่งมอบล่าช้า (`sla_delay_risk`) เทียบกับ milestone/deadline ของโครงการ
   ถ้าเสี่ยงสูง ระบบแนะนำ vendor สำรอง (เทียบจาก `rating` ใน `vendors` ที่เป็นหมวดเดียวกัน)

---

## 4. โมดูลงานสัญญา (Contract Lifecycle) — ตารางใหม่

### 4.1 `contracts` — เก็บร่างสัญญาและผล Redline

```sql
CREATE TABLE contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    contract_text TEXT,
    version INTEGER DEFAULT 1,
    redline_result JSON,        -- AI: [{clause, risk_level, issue, counter_proposal}]
    overall_risk_summary TEXT,
    uploaded_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects (id)
);
```

### 4.2 `obligations` — Milestone & Obligation Tracker (ขยายจาก `milestones` เดิม)

```sql
CREATE TABLE obligations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    obligation_text TEXT,        -- เช่น "ส่งรายงานความคืบหน้าภายใน 15 วันหลังจบขั้นที่ 2"
    category TEXT,               -- deliverable / payment / reporting / insurance / legal / other
    responsible_party TEXT,      -- 'ผู้รับจ้าง' หรือ 'ผู้ว่าจ้าง'
    due_date_or_trigger TEXT,    -- วันที่แน่นอน หรือเงื่อนไขทริกเกอร์
    penalty_if_missed TEXT,
    status TEXT DEFAULT 'pending',  -- pending / in_progress / done / overdue
    linked_milestone_id INTEGER,    -- เชื่อมกับ milestones.id ถ้าเป็น obligation ที่ตรงกับ deliverable
    created_at TEXT,
    FOREIGN KEY (contract_id) REFERENCES contracts (id),
    FOREIGN KEY (linked_milestone_id) REFERENCES milestones (id)
);
```

**Workflow — Contract Redlining:**
1. ได้รับร่างสัญญาจากคู่ค้า → วาง/อัปโหลดเข้า `contracts.contract_text`
2. AI สแกนทั้งฉบับ หา clause เสี่ยง: ค่าปรับเกินมาตรฐาน, เงื่อนไข IP ไม่เป็นธรรม, เงื่อนไขงวดเงินไม่ตรงที่คุยไว้
   → บันทึกเป็น `redline_result` (list ของ clause + risk_level + ข้อเสนอแย้ง)
3. ฝ่ายกฎหมาย/ผู้บริหารเข้ามาดู highlight ในหน้าเว็บ อนุมัติ/ส่งกลับแก้กับคู่ค้า

**Workflow — Obligation Tracker:**
1. จากสัญญาฉบับสุดท้าย (หรือ TOR ถ้ายังไม่มีสัญญาเป็นทางการ) AI สกัดข้อผูกมัดทั้งหมดออกเป็น `obligations`
   ซึ่งกว้างกว่า `milestones` เดิม (ครอบคลุมเรื่อง reporting, insurance, legal ไม่ใช่แค่ deliverable)
2. ระบบเทียบ `due_date_or_trigger` กับวันปัจจุบัน → ตั้งสถานะ `overdue` อัตโนมัติถ้าเลยกำหนดและยังไม่ `done`
3. (Phase ถัดไป) ส่งต่อไปสร้าง task ใน Jira/Trello/Asana ผ่าน connector — ยังไม่รวมในเวอร์ชันนี้

---

## 5. ความสัมพันธ์ตารางทั้งหมด (Entity Relationship)

```
company_profile (1)

projects (1) ──< milestones
projects (1) ──< boms (1) ──< bom_items
projects (1) ──< competitors
projects (1) ──< rfqs ──< rfq_items
                    │
                    └──< vendor_quotes >── vendors
projects (1) ──< contracts (1) ──< obligations >── milestones (linked_milestone_id)
```

---

## 6. การแบ่งงานตาม Tool (ตามที่ผู้ใช้ระบุ)

| Tool | บทบาท | โมดูลที่เกี่ยวข้อง |
|---|---|---|
| **Claude AI** (ผ่าน `ai_engine.py` ในแอปนี้) | อ่านเอกสารยาว วิเคราะห์ความเสี่ยง จับคู่สเปค เขียน proposal, redline สัญญา | ทุกโมดูล — เป็น "สมองกล" หลักที่ implement แล้วในแอปปัจจุบัน |
| **Claude Code** | พัฒนา web platform, PDF/DOCX parser, RAG/vector DB สำหรับค้นย้อนหลัง, API layer | โครงสร้างแอป Streamlit + db.py ปัจจุบันเทียบเท่าจุดเริ่มต้นของงานนี้ ส่วน RAG/vector DB ยังไม่ได้ทำ |
| **Claude Coworker / connector** | ดึงข้อมูล e-GP, ส่งอีเมลหา vendor, ตั้งเตือนปฏิทิน, sync CRM/ERP | **ยังไม่รวมในแอปเวอร์ชันนี้** — ต้องต่อ MCP connector ภายนอก (Gmail, Google Calendar, e-GP scraping) เพิ่มเติม |

## 7. โมดูล Login / RBAC / Multi-user (implement แล้ว)

### 7.1 `departments`, `users`, `audit_log`

```sql
CREATE TABLE departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at TEXT
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    password_hash TEXT NOT NULL,   -- PBKDF2-SHA256, 200k รอบ, เก็บเป็น "salt$hash" (hex)
    role TEXT NOT NULL DEFAULT 'sales',   -- admin / sales / procurement / legal
    department_id INTEGER,
    is_active INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (department_id) REFERENCES departments (id)
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    user_email TEXT,
    action TEXT,           -- login / logout / create_project / change_status / create_user / ...
    entity_type TEXT,      -- project / user / ...
    entity_id INTEGER,
    details TEXT,
    created_at TEXT
);
```

`projects` เพิ่มคอลัมน์ `department_id` และ `created_by_user_id` (migration แบบ `ALTER TABLE ... ADD COLUMN` ที่ตรวจสอบก่อนว่ามีคอลัมน์อยู่แล้วหรือยัง เพื่อไม่ทำลายฐานข้อมูลเดิมที่มีอยู่)

### 7.2 Role → หน้าที่เข้าถึงได้ (page-level RBAC)

| Role | ความหมาย | หน้าที่เข้าถึง |
|---|---|---|
| `admin` | ผู้ดูแลระบบ | ทุกหน้า รวมถึงจัดการผู้ใช้ |
| `sales` | ฝ่ายขาย | Dashboard, วิเคราะห์ TOR, โครงการทั้งหมด (แก้ไขได้), บริหารสัญญา |
| `procurement` | ฝ่ายจัดซื้อ | Dashboard, โครงการทั้งหมด (ดูอย่างเดียว), บริหารสัญญา, จัดซื้อ/RFQ |
| `legal` | ฝ่ายกฎหมาย/สัญญา | Dashboard, โครงการทั้งหมด (ดูอย่างเดียว), ตรวจสัญญา |

บังคับใช้ผ่าน `auth.require_role([...])` ที่บนสุดของทุกไฟล์ใน `pages/*.py` — ถ้า role ไม่ตรง ระบบเด้งข้อความ "ไม่มีสิทธิ์" และหยุดการทำงานของสคริปต์หน้านั้นทันที (ไม่ใช่แค่ซ่อน UI)

### 7.3 Workflow — Login & session

```
ผู้ใช้เปิด URL แอป
        │
        ▼
auth.require_login() ── ยังไม่ login ──▶ แสดงฟอร์ม login → ตรวจสอบ email+password (PBKDF2 verify)
        │                                     │ ผ่าน → เก็บ user ลง st.session_state → rerun
        │ login แล้ว
        ▼
auth.require_role([...]) ── role ไม่ตรง ──▶ แสดง "ไม่มีสิทธิ์" + ปุ่ม logout → st.stop()
        │ role ตรง (หรือเป็น admin)
        ▼
   แสดงเนื้อหาหน้านั้นตามปกติ
```

`st.session_state` ของ Streamlit แยกตาม browser session อยู่แล้ว จึงรองรับหลายคน login พร้อมกันได้ทันทีเมื่อ deploy เป็นเซิร์ฟเวอร์กลาง โดยไม่ต้องเขียนโค้ดจัดการ concurrency เพิ่มในส่วนนี้

### 7.4 Bootstrap admin คนแรก

`auth.bootstrap()` ถูกเรียกทุกครั้งที่โหลดหน้า — ถ้า `db.count_users() == 0` จะสร้าง admin จากค่า `DEFAULT_ADMIN_EMAIL`/`DEFAULT_ADMIN_PASSWORD` ใน `.env` ให้อัตโนมัติ (ครั้งเดียว) เพื่อให้มีทางเข้าระบบครั้งแรกเสมอโดยไม่ต้องรัน script แยก

### 7.5 สิ่งที่ยังไม่ทำในเวอร์ชันนี้ (ต่อยอดได้)

- **Row-level scoping ตามส่วนงาน** — ตอนนี้กรองสิทธิ์ระดับหน้าเท่านั้น ทุกคนใน role เดียวกันเห็นทุกโครงการ ถ้าต้องการจำกัดว่าเห็นเฉพาะโครงการของส่วนงานตัวเอง ให้ filter `db.list_projects()` ด้วย `department_id` (คอลัมน์มีอยู่แล้วในตาราง `projects`)
- **SSO / OIDC** — ตอนนี้ใช้ username/password เก็บเอง เปลี่ยนไปใช้ `st.login()` ผูกกับ Google/Microsoft ได้โดยไม่ต้องแก้ schema
- **Tab-level restriction ภายในหน้าเดียวกัน** — เช่นให้ procurement แก้ไขได้เฉพาะบางส่วนของหน้าโครงการทั้งหมด ตอนนี้เป็น all-or-nothing (ดูได้ทั้งหมด/แก้ไขได้ทั้งหมด) ต่อหนึ่งหน้า

## 8. Inbox TOR Watcher — หางานเชิงรุกจากอีเมล (implement แล้ว)

เดิมทีมองไว้ว่าจะ "กวาดหา" TOR จาก e-GP/บริษัทเอกชนแบบ crawl ทั้งเว็บ แต่หลังประเมินแล้วพบว่า:
RFP ของเอกชนไม่มีแหล่งกลางสาธารณะให้ค้น (ส่งตรงถึงบริษัทที่ถูกเชิญเท่านั้น) และ e-GP มี API ทางการ
เฉพาะข้อมูลสัญญาที่ประมูลเสร็จแล้ว (govspending.data.go.th) ไม่ใช่ประกาศที่เปิดอยู่ปัจจุบัน ส่วนการ scrape
หน้าเว็บ e-GP โดยตรงยังไม่มีนโยบายชัดเจนเรื่อง automated access จึงเลี่ยงไว้ก่อน

ทางเลือกที่คุ้มค่าและทำได้จริงทันทีคือ **เฝ้าดูอินบ็อกซ์อีเมลของบริษัทเอง** เพราะ RFP เอกชนส่วนใหญ่ถูกส่ง
เข้ามาทางอีเมลอยู่แล้ว การดึงข้อมูลจากอีเมลของตัวเองไม่มีประเด็นด้าน ToS/กฎหมายแบบการ scrape เว็บภายนอก

### 8.1 `email_leads`

```sql
CREATE TABLE email_leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_message_id TEXT UNIQUE,   -- กันสแกนซ้ำ
    sender TEXT,
    subject TEXT,
    received_at TEXT,
    attachment_names TEXT,
    status TEXT DEFAULT 'new',      -- new / imported / dismissed
    linked_project_id INTEGER,      -- โครงการที่ถูกสร้างขึ้นถ้ากด "นำเข้า"
    scanned_at TEXT,
    FOREIGN KEY (linked_project_id) REFERENCES projects (id)
);
```

### 8.2 Workflow

```
ผู้ใช้ (sales/admin) เชื่อมต่อ Gmail ครั้งแรก (OAuth, ขอสิทธิ์ read-only)
                │
                ▼
กด "สแกนอีเมลตอนนี้" (ระบุคีย์เวิร์ด + ช่วงวันย้อนหลัง)
                │
                ▼
Gmail API ค้นหา: has:attachment (keyword1 OR keyword2 ...) newer_than:Nd
                │
                ▼
บันทึกผลลัพธ์ลง email_leads (status='new', dedupe ด้วย gmail_message_id)
                │
                ▼
ผู้ใช้ตรวจรายการ → เลือก "นำเข้าเป็นโครงการ" รายที่สนใจ
                │
                ▼
ดึงไฟล์แนบ (PDF/DOCX) → รวมข้อความ → ai_engine.analyze_tor()
                │
                ▼
db.create_project() + db.update_project(tor_analysis=...)
status='imported', linked_project_id=โครงการใหม่
                │
                ▼
เข้าสู่ pipeline ปกติ: ประเมินความเสี่ยง → โอกาสชนะงาน (Bid/No-Bid) → ...
```

### 8.3 ทำไมไม่ทำเป็น auto-scan อัตโนมัติเต็มรูปแบบ (ไม่มี human-in-the-loop)

ตั้งใจให้ผู้ใช้กด "นำเข้า" เองทีละรายการ แทนที่จะสร้างโครงการอัตโนมัติทุกอีเมลที่ตรงคีย์เวิร์ด เพราะ:
- คีย์เวิร์ดอาจ false-positive (อีเมลที่พูดถึงคำว่า TOR แต่ไม่ใช่ RFP จริง) การให้คนกรองก่อนสร้างโครงการช่วยลดขยะในระบบ
- การตัดสินใจ Bid/No-Bid เป็นเรื่องธุรกิจที่ควรมีคนรับผิดชอบ ไม่ใช่ระบบสร้างโครงการเองแบบเงียบๆ

ถ้าต้องการให้สแกนอัตโนมัติเป็นตารางเวลา (ไม่ต้องกดเอง) ต้องแยกสคริปต์ที่เรียก `email_watcher.py` มารันผ่าน
cron/Task Scheduler ของ OS ที่ deploy อยู่ — ยังไม่รวมมาให้ในเวอร์ชันนี้

## 9. e-GP Market Intelligence (implement แล้ว)

ใช้ API เปิดเผยอย่างเป็นทางการของกรมบัญชีกลาง — บริการ `CGDContract` ผ่าน `govspending.data.go.th`
(endpoint จริง: `https://opend.data.go.th/govspending/cgdcontract`) **ไม่ใช่การ scrape เว็บ** ข้อมูลที่ได้คือ
สัญญาที่ประมูล**เสร็จแล้ว** เท่านั้น (ไม่มี live feed ของประกาศที่เปิดรับอยู่ตอนนี้จาก API ทางการ)

### 9.1 พารามิเตอร์ที่ยืนยันได้จากเอกสาร/ตัวอย่างสาธารณะ

`api-key` (จำเป็น), `year`, `dept_code`, `budget_start`, `budget_end`, `offset`, `keyword`, `winner_tin`

Response ที่ยืนยันได้: `code`, `status`, `msg`, `time`, `param_obj`, `summary` (มี `total_project`,
`total_price`) และ record แต่ละรายการมี field: `project_id`, `project_name`, `project_type_name`,
`dept_name`, `dept_sub_name`, `purchase_method_name`, `purchase_method_group_name`, `announce_date`

### 9.2 ⚠️ ข้อจำกัดที่ต้องรู้: field ผู้ชนะ/ราคายังไม่ยืนยัน 100%

ตอนพัฒนาไม่สามารถหาตัวอย่าง response ที่มี field ชื่อผู้ชนะและราคาสัญญาที่ชัดเจนได้ (เอกสาร API
อย่างเป็นทางการเป็นหน้าเว็บที่ render ด้วย JavaScript ทำให้ดึงเนื้อหามาตรวจสอบโดยตรงไม่ได้ในตอนพัฒนา)
`egp_intelligence.py` จึงลองไล่หา key ที่เป็นไปได้หลายชื่อ:

```python
WINNER_FIELD_CANDIDATES = ["winner_name", "winner", "winner_tin_name", "company_name", "vendor_name"]
PRICE_FIELD_CANDIDATES = ["sum_price_agree", "price_agree", "contract_price", "price", "budget"]
```

และ**เก็บ raw JSON ของทุกรายการไว้เสมอ** ให้ผู้ใช้ตรวจสอบใน UI (expander "ข้อมูลดิบ") — ถ้า mapping ผิด
ให้แก้ list ทั้งสองใน `egp_intelligence.py` ให้ตรงกับ field จริงที่เห็นใน raw JSON ครั้งแรกที่ทดลองยิง API จริง

### 9.3 Workflow

```
ผู้ใช้กรอกคีย์เวิร์ด/เลขผู้เสียภาษีคู่แข่ง/หน่วยงาน/ปี/ช่วงงบ
                │
                ▼
egp_intelligence.search_contracts() → GET govspending API
                │
                ▼
แสดงผลลัพธ์ + raw JSON ให้ตรวจสอบ
                │
                ▼
ผู้ใช้เลือกโครงการในระบบ + ตั้งชื่อคู่แข่ง → กด "บันทึกเป็นคู่แข่ง"
                │
                ▼
egp_intelligence.summarize_for_competitor() สรุปผลเป็นข้อความ
                │
                ▼
ai_engine.analyze_competitor() วิเคราะห์จุดข่ม (ฟังก์ชันเดิมที่มีอยู่แล้ว)
                │
                ▼
db.add_competitor() บันทึกลงแท็บ "คู่แข่ง" ของโครงการ (source='e-GP Open Data')
```

ใช้ AI function เดิม (`analyze_competitor`) และตาราง `competitors` เดิมที่มีอยู่แล้ว — ไม่ต้องเพิ่ม schema ใหม่

## 10. ข้อจำกัดปัจจุบันของ MVP นี้ (สิ่งที่ยังไม่ทำอัตโนมัติ)

- **ไม่ดึงข้อมูล e-GP อัตโนมัติ** — ผู้ใช้ต้องนำข้อมูลคู่แข่ง/ราคากลางมาวางเอง ให้ AI วิเคราะห์ต่อ
- **ไม่ส่งอีเมล RFQ หา vendor อัตโนมัติ** — ผู้ใช้วาง/อัปโหลดใบเสนอราคาที่ได้รับมาแล้วเข้าระบบเอง
- **ไม่ sync กับ Jira/Trello/Asana/CRM/ERP** — ต้องต่อ connector เพิ่มเป็นเฟสถัดไป
- **ไม่มีระบบแจ้งเตือนอัตโนมัติ (push/email)** — สถานะ overdue คำนวณจากวันที่เทียบ ณ ตอนเปิดหน้าเว็บเท่านั้น
- โมดูลเหล่านี้ทำได้จริงด้วยการต่อ MCP connector ที่มีอยู่แล้ว (Gmail, Calendar) ในภายหลัง โดยไม่ต้องเปลี่ยน schema

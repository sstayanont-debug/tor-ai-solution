"""
db.py — SQLite persistence layer for TOR AI Solution
เก็บข้อมูลโปรไฟล์บริษัท, โครงการที่วิเคราะห์, และ milestone ของสัญญา
"""

import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tor_ai.db")


def _ensure_data_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def get_conn():
    _ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS company_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                company_name TEXT,
                experience_years TEXT,
                certifications TEXT,
                past_projects TEXT,
                team_size TEXT,
                financial_capacity TEXT,
                core_competencies TEXT,
                updated_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tor_text TEXT,
                tor_analysis TEXT,
                risk_assessment TEXT,
                win_probability TEXT,
                sales_support TEXT,
                status TEXT DEFAULT 'analyzing',
                created_at TEXT,
                updated_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT,
                due_date TEXT,
                deliverable TEXT,
                payment_percent TEXT,
                status TEXT DEFAULT 'pending',
                notes TEXT,
                created_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id)
            )
        """)

        # ---------------- Sales & Pipeline ----------------
        c.execute("""
            CREATE TABLE IF NOT EXISTS boms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                solution_architecture_summary TEXT,
                total_cost_estimate REAL,
                total_price_estimate REAL,
                target_margin_percent REAL,
                actual_margin_percent REAL,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS bom_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bom_id INTEGER NOT NULL,
                category TEXT,
                item_name TEXT,
                spec TEXT,
                qty REAL,
                unit TEXT,
                unit_cost REAL,
                unit_price REAL,
                source TEXT,
                FOREIGN KEY (bom_id) REFERENCES boms (id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS competitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                competitor_name TEXT,
                past_win_rate TEXT,
                estimated_bid_price TEXT,
                strengths TEXT,
                weaknesses TEXT,
                source TEXT,
                ai_differentiator_suggestions TEXT,
                created_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id)
            )
        """)

        # ---------------- Procurement ----------------
        c.execute("""
            CREATE TABLE IF NOT EXISTS vendors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_name TEXT,
                category TEXT,
                contact_info TEXT,
                rating REAL,
                notes TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS rfqs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                bom_id INTEGER,
                title TEXT,
                deadline TEXT,
                status TEXT DEFAULT 'draft',
                created_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id),
                FOREIGN KEY (bom_id) REFERENCES boms (id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS rfq_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfq_id INTEGER NOT NULL,
                item_name TEXT,
                spec TEXT,
                qty REAL,
                unit TEXT,
                FOREIGN KEY (rfq_id) REFERENCES rfqs (id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS vendor_quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfq_id INTEGER NOT NULL,
                vendor_id INTEGER,
                vendor_name_freeform TEXT,
                raw_quote_text TEXT,
                ai_extracted TEXT,
                total_price REAL,
                delivery_days INTEGER,
                spec_match_percent REAL,
                sla_delay_risk TEXT,
                sla_risk_reason TEXT,
                status TEXT DEFAULT 'pending',
                submitted_at TEXT,
                FOREIGN KEY (rfq_id) REFERENCES rfqs (id),
                FOREIGN KEY (vendor_id) REFERENCES vendors (id)
            )
        """)

        # ---------------- Contract Lifecycle ----------------
        c.execute("""
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                contract_text TEXT,
                version INTEGER DEFAULT 1,
                redline_result TEXT,
                overall_risk_summary TEXT,
                uploaded_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects (id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS obligations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER NOT NULL,
                obligation_text TEXT,
                category TEXT,
                responsible_party TEXT,
                due_date_or_trigger TEXT,
                penalty_if_missed TEXT,
                status TEXT DEFAULT 'pending',
                linked_milestone_id INTEGER,
                created_at TEXT,
                FOREIGN KEY (contract_id) REFERENCES contracts (id),
                FOREIGN KEY (linked_milestone_id) REFERENCES milestones (id)
            )
        """)

        # ---------------- Auth / Users / Departments / Audit ----------------
        c.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'sales',
                department_id INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (department_id) REFERENCES departments (id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_email TEXT,
                action TEXT,
                entity_type TEXT,
                entity_id INTEGER,
                details TEXT,
                created_at TEXT
            )
        """)

        # ---------------- Inbox TOR Watcher ----------------
        c.execute("""
            CREATE TABLE IF NOT EXISTS email_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gmail_message_id TEXT UNIQUE,
                sender TEXT,
                subject TEXT,
                received_at TEXT,
                attachment_names TEXT,
                status TEXT DEFAULT 'new',
                linked_project_id INTEGER,
                scanned_at TEXT,
                FOREIGN KEY (linked_project_id) REFERENCES projects (id)
            )
        """)

        # ---------------- Migration: add ownership columns to existing tables ----------------
        _ensure_column(conn, "projects", "department_id", "INTEGER")
        _ensure_column(conn, "projects", "created_by_user_id", "INTEGER")


def _ensure_column(conn, table: str, column: str, coltype: str):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


# ---------------- Company profile ----------------

def get_company_profile():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM company_profile WHERE id = 1").fetchone()
        return dict(row) if row else None


def save_company_profile(data: dict):
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM company_profile WHERE id = 1").fetchone()
        now = datetime.now().isoformat()
        if existing:
            conn.execute("""
                UPDATE company_profile SET company_name=?, experience_years=?, certifications=?,
                    past_projects=?, team_size=?, financial_capacity=?, core_competencies=?, updated_at=?
                WHERE id = 1
            """, (
                data.get("company_name", ""), data.get("experience_years", ""),
                data.get("certifications", ""), data.get("past_projects", ""),
                data.get("team_size", ""), data.get("financial_capacity", ""),
                data.get("core_competencies", ""), now
            ))
        else:
            conn.execute("""
                INSERT INTO company_profile
                (id, company_name, experience_years, certifications, past_projects,
                 team_size, financial_capacity, core_competencies, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("company_name", ""), data.get("experience_years", ""),
                data.get("certifications", ""), data.get("past_projects", ""),
                data.get("team_size", ""), data.get("financial_capacity", ""),
                data.get("core_competencies", ""), now
            ))


# ---------------- Projects ----------------

def create_project(name: str, tor_text: str, created_by_user_id: int = None, department_id: int = None) -> int:
    with get_conn() as conn:
        now = datetime.now().isoformat()
        cur = conn.execute("""
            INSERT INTO projects (name, tor_text, status, created_at, updated_at, created_by_user_id, department_id)
            VALUES (?, ?, 'analyzing', ?, ?, ?, ?)
        """, (name, tor_text, now, now, created_by_user_id, department_id))
        return cur.lastrowid


def update_project(project_id: int, **fields):
    if not fields:
        return
    allowed = {"tor_analysis", "risk_assessment", "win_probability", "sales_support", "status", "name"}
    sets, values = [], []
    for k, v in fields.items():
        if k in allowed:
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            sets.append(f"{k} = ?")
            values.append(v)
    if not sets:
        return
    sets.append("updated_at = ?")
    values.append(datetime.now().isoformat())
    values.append(project_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", values)


def get_project(project_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        for field in ("tor_analysis", "risk_assessment", "win_probability", "sales_support"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d


def list_projects():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]


def delete_project(project_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM milestones WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))


# ---------------- Milestones ----------------

def add_milestones(project_id: int, milestones: list):
    with get_conn() as conn:
        now = datetime.now().isoformat()
        for m in milestones:
            conn.execute("""
                INSERT INTO milestones (project_id, title, due_date, deliverable, payment_percent, status, notes, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """, (
                project_id, m.get("title", ""), m.get("due_date_or_offset", ""),
                m.get("deliverable", ""), str(m.get("payment_percent", "")),
                m.get("notes", ""), now
            ))


def get_milestones(project_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM milestones WHERE project_id = ? ORDER BY id ASC", (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_milestone_status(milestone_id: int, status: str, notes: str = None):
    with get_conn() as conn:
        if notes is not None:
            conn.execute("UPDATE milestones SET status = ?, notes = ? WHERE id = ?", (status, notes, milestone_id))
        else:
            conn.execute("UPDATE milestones SET status = ? WHERE id = ?", (status, milestone_id))


def delete_milestone(milestone_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM milestones WHERE id = ?", (milestone_id,))


# ---------------- BOM / Costing ----------------

def create_bom(project_id: int, solution_architecture_summary: str = "", notes: str = "") -> int:
    with get_conn() as conn:
        now = datetime.now().isoformat()
        cur = conn.execute("""
            INSERT INTO boms (project_id, solution_architecture_summary, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, solution_architecture_summary, notes, now, now))
        return cur.lastrowid


def add_bom_items(bom_id: int, items: list):
    with get_conn() as conn:
        for it in items:
            conn.execute("""
                INSERT INTO bom_items (bom_id, category, item_name, spec, qty, unit, unit_cost, unit_price, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bom_id, it.get("category", ""), it.get("item_name", ""), it.get("spec", ""),
                it.get("qty", 0) or 0, it.get("unit", ""), it.get("unit_cost", 0) or 0,
                it.get("unit_price", 0) or 0, it.get("source", "ai_estimate"),
            ))


def get_bom_for_project(project_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM boms WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)
        ).fetchone()
        return dict(row) if row else None


def get_bom_items(bom_id: int):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM bom_items WHERE bom_id = ? ORDER BY id ASC", (bom_id,)).fetchall()
        return [dict(r) for r in rows]


def update_bom_item(item_id: int, **fields):
    allowed = {"category", "item_name", "spec", "qty", "unit", "unit_cost", "unit_price", "source"}
    sets, values = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            values.append(v)
    if not sets:
        return
    values.append(item_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE bom_items SET {', '.join(sets)} WHERE id = ?", values)


def recalc_bom_totals(bom_id: int):
    with get_conn() as conn:
        items = conn.execute("SELECT qty, unit_cost, unit_price FROM bom_items WHERE bom_id = ?", (bom_id,)).fetchall()
        total_cost = sum((r["qty"] or 0) * (r["unit_cost"] or 0) for r in items)
        total_price = sum((r["qty"] or 0) * (r["unit_price"] or 0) for r in items)
        margin = ((total_price - total_cost) / total_price * 100) if total_price else 0
        conn.execute(
            "UPDATE boms SET total_cost_estimate=?, total_price_estimate=?, actual_margin_percent=?, updated_at=? WHERE id=?",
            (total_cost, total_price, margin, datetime.now().isoformat(), bom_id)
        )
        return {"total_cost": total_cost, "total_price": total_price, "margin_percent": margin}


def delete_bom_item(item_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM bom_items WHERE id = ?", (item_id,))


# ---------------- Competitor Intelligence ----------------

def add_competitor(project_id: int, data: dict) -> int:
    with get_conn() as conn:
        now = datetime.now().isoformat()
        cur = conn.execute("""
            INSERT INTO competitors (project_id, competitor_name, past_win_rate, estimated_bid_price,
                strengths, weaknesses, source, ai_differentiator_suggestions, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id, data.get("competitor_name", ""), data.get("past_win_rate", ""),
            data.get("estimated_bid_price", ""), data.get("strengths", ""), data.get("weaknesses", ""),
            data.get("source", ""), data.get("ai_differentiator_suggestions", ""), now,
        ))
        return cur.lastrowid


def get_competitors(project_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM competitors WHERE project_id = ? ORDER BY id DESC", (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_competitor_ai_suggestion(competitor_id: int, suggestion: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE competitors SET ai_differentiator_suggestions = ? WHERE id = ?", (suggestion, competitor_id)
        )


def delete_competitor(competitor_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM competitors WHERE id = ?", (competitor_id,))


# ---------------- Vendors ----------------

def add_vendor(data: dict) -> int:
    with get_conn() as conn:
        now = datetime.now().isoformat()
        cur = conn.execute("""
            INSERT INTO vendors (vendor_name, category, contact_info, rating, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data.get("vendor_name", ""), data.get("category", ""), data.get("contact_info", ""),
            data.get("rating", 0) or 0, data.get("notes", ""), now,
        ))
        return cur.lastrowid


def list_vendors(category: str = None):
    with get_conn() as conn:
        if category:
            rows = conn.execute("SELECT * FROM vendors WHERE category = ? ORDER BY rating DESC", (category,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM vendors ORDER BY vendor_name ASC").fetchall()
        return [dict(r) for r in rows]


# ---------------- RFQ / Procurement ----------------

def create_rfq(project_id: int, title: str, bom_id: int = None, deadline: str = "") -> int:
    with get_conn() as conn:
        now = datetime.now().isoformat()
        cur = conn.execute("""
            INSERT INTO rfqs (project_id, bom_id, title, deadline, status, created_at)
            VALUES (?, ?, ?, ?, 'draft', ?)
        """, (project_id, bom_id, title, deadline, now))
        return cur.lastrowid


def add_rfq_items(rfq_id: int, items: list):
    with get_conn() as conn:
        for it in items:
            conn.execute("""
                INSERT INTO rfq_items (rfq_id, item_name, spec, qty, unit) VALUES (?, ?, ?, ?, ?)
            """, (rfq_id, it.get("item_name", ""), it.get("spec", ""), it.get("qty", 0) or 0, it.get("unit", "")))


def get_rfqs_for_project(project_id: int):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM rfqs WHERE project_id = ? ORDER BY id DESC", (project_id,)).fetchall()
        return [dict(r) for r in rows]


def get_rfq(rfq_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM rfqs WHERE id = ?", (rfq_id,)).fetchone()
        return dict(row) if row else None


def get_rfq_items(rfq_id: int):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM rfq_items WHERE rfq_id = ? ORDER BY id ASC", (rfq_id,)).fetchall()
        return [dict(r) for r in rows]


def update_rfq_status(rfq_id: int, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE rfqs SET status = ? WHERE id = ?", (status, rfq_id))


def add_vendor_quote(rfq_id: int, data: dict) -> int:
    with get_conn() as conn:
        now = datetime.now().isoformat()
        ai_extracted = data.get("ai_extracted")
        if isinstance(ai_extracted, (dict, list)):
            ai_extracted = json.dumps(ai_extracted, ensure_ascii=False)
        cur = conn.execute("""
            INSERT INTO vendor_quotes (rfq_id, vendor_id, vendor_name_freeform, raw_quote_text, ai_extracted,
                total_price, delivery_days, spec_match_percent, sla_delay_risk, sla_risk_reason, status, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            rfq_id, data.get("vendor_id"), data.get("vendor_name_freeform", ""), data.get("raw_quote_text", ""),
            ai_extracted, data.get("total_price"), data.get("delivery_days"), data.get("spec_match_percent"),
            data.get("sla_delay_risk", ""), data.get("sla_risk_reason", ""), now,
        ))
        return cur.lastrowid


def get_vendor_quotes(rfq_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM vendor_quotes WHERE rfq_id = ? ORDER BY total_price ASC", (rfq_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("ai_extracted"):
                try:
                    d["ai_extracted"] = json.loads(d["ai_extracted"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result


def select_vendor_quote(quote_id: int, rfq_id: int):
    """Mark one quote as selected and reject the rest for the same RFQ."""
    with get_conn() as conn:
        conn.execute("UPDATE vendor_quotes SET status = 'rejected' WHERE rfq_id = ?", (rfq_id,))
        conn.execute("UPDATE vendor_quotes SET status = 'selected' WHERE id = ?", (quote_id,))


# ---------------- Contracts & Obligations ----------------

def create_contract(project_id: int, contract_text: str) -> int:
    with get_conn() as conn:
        now = datetime.now().isoformat()
        cur = conn.execute("""
            INSERT INTO contracts (project_id, contract_text, version, uploaded_at)
            VALUES (?, ?, 1, ?)
        """, (project_id, contract_text, now))
        return cur.lastrowid


def update_contract_redline(contract_id: int, redline_result, overall_risk_summary: str):
    if isinstance(redline_result, (dict, list)):
        redline_result = json.dumps(redline_result, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            "UPDATE contracts SET redline_result = ?, overall_risk_summary = ? WHERE id = ?",
            (redline_result, overall_risk_summary, contract_id)
        )


def get_contracts_for_project(project_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contracts WHERE project_id = ? ORDER BY id DESC", (project_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("redline_result"):
                try:
                    d["redline_result"] = json.loads(d["redline_result"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result


def add_obligations(contract_id: int, obligations: list):
    with get_conn() as conn:
        now = datetime.now().isoformat()
        for o in obligations:
            conn.execute("""
                INSERT INTO obligations (contract_id, obligation_text, category, responsible_party,
                    due_date_or_trigger, penalty_if_missed, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (
                contract_id, o.get("obligation_text", ""), o.get("category", ""),
                o.get("responsible_party", ""), o.get("due_date_or_trigger", ""),
                o.get("penalty_if_missed", ""), now,
            ))


def get_obligations(contract_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM obligations WHERE contract_id = ? ORDER BY id ASC", (contract_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_obligation_status(obligation_id: int, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE obligations SET status = ? WHERE id = ?", (status, obligation_id))


# ---------------- Departments ----------------

def create_department(name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO departments (name, created_at) VALUES (?, ?)",
            (name, datetime.now().isoformat())
        )
        row = conn.execute("SELECT id FROM departments WHERE name = ?", (name,)).fetchone()
        return row["id"] if row else cur.lastrowid


def list_departments():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM departments ORDER BY name ASC").fetchall()
        return [dict(r) for r in rows]


def get_department(department_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM departments WHERE id = ?", (department_id,)).fetchone()
        return dict(row) if row else None


# ---------------- Users ----------------

def create_user(email: str, name: str, password_hash: str, role: str, department_id: int = None, is_active: bool = True) -> int:
    with get_conn() as conn:
        now = datetime.now().isoformat()
        cur = conn.execute("""
            INSERT INTO users (email, name, password_hash, role, department_id, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (email.strip().lower(), name, password_hash, role, department_id, 1 if is_active else 0, now, now))
        return cur.lastrowid


def get_user_by_email(email: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        return dict(row) if row else None


def get_user(user_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_users():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT u.*, d.name AS department_name FROM users u
            LEFT JOIN departments d ON u.department_id = d.id
            ORDER BY u.created_at ASC
        """).fetchall()
        return [dict(r) for r in rows]


def update_user(user_id: int, **fields):
    allowed = {"name", "role", "department_id", "is_active", "password_hash"}
    sets, values = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            values.append(v)
    if not sets:
        return
    sets.append("updated_at = ?")
    values.append(datetime.now().isoformat())
    values.append(user_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", values)


def count_users() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        return row["c"]


def ensure_default_admin(email: str, name: str, password_hash: str):
    """สร้าง admin เริ่มต้นถ้ายังไม่มี user ใดในระบบเลย (bootstrap ครั้งแรก)"""
    if count_users() == 0:
        create_user(email, name, password_hash, role="admin", department_id=None, is_active=True)


# ---------------- Audit log ----------------

def log_audit(user_id, user_email, action: str, entity_type: str = "", entity_id: int = None, details: str = ""):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO audit_log (user_id, user_email, action, entity_type, entity_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, user_email, action, entity_type, entity_id, details, datetime.now().isoformat()))


def get_audit_log(limit: int = 200):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


# ---------------- Email leads (Inbox TOR Watcher) ----------------

def upsert_email_lead(gmail_message_id: str, sender: str, subject: str, received_at: str, attachment_names: list):
    with get_conn() as conn:
        now = datetime.now().isoformat()
        conn.execute("""
            INSERT OR IGNORE INTO email_leads
                (gmail_message_id, sender, subject, received_at, attachment_names, status, scanned_at)
            VALUES (?, ?, ?, ?, ?, 'new', ?)
        """, (gmail_message_id, sender, subject, received_at, ", ".join(attachment_names), now))
        row = conn.execute("SELECT id FROM email_leads WHERE gmail_message_id = ?", (gmail_message_id,)).fetchone()
        return row["id"] if row else None


def list_email_leads(status: str = None):
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM email_leads WHERE status = ? ORDER BY id DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM email_leads ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


def update_email_lead_status(lead_id: int, status: str, linked_project_id: int = None):
    with get_conn() as conn:
        if linked_project_id is not None:
            conn.execute(
                "UPDATE email_leads SET status = ?, linked_project_id = ? WHERE id = ?",
                (status, linked_project_id, lead_id)
            )
        else:
            conn.execute("UPDATE email_leads SET status = ? WHERE id = ?", (status, lead_id))

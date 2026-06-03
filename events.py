"""
Nursify Event Registration
FastAPI APIRouter — prefix /events
"""

import csv
import io
import logging
import os
import secrets
import smtplib
import psycopg2
import psycopg2.extras
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, EmailStr

log = logging.getLogger("nursify.events")

DATABASE_URL    = os.environ.get("DATABASE_URL", "")
GMAIL_USER      = os.environ.get("GMAIL_USER", "nursifyaesthetics@gmail.com")
GMAIL_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD", "")
ADMIN_PASSWORD  = os.environ.get("ADMIN_PASSWORD", "")

router = APIRouter(prefix="/events", tags=["events"])
security = HTTPBasic()


# ── DB helpers ─────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_events_db():
    if not DATABASE_URL:
        log.warning("DATABASE_URL not set — events tables not created")
        return
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS events_events (
                id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name                  TEXT NOT NULL,
                event_date            TIMESTAMPTZ NOT NULL,
                registration_deadline TIMESTAMPTZ NOT NULL,
                description           TEXT,
                medical_clearance_note TEXT,
                active                BOOLEAN DEFAULT TRUE,
                created_at            TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS events_registrations (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                event_id        UUID REFERENCES events_events(id),
                full_name       TEXT NOT NULL,
                dob             DATE NOT NULL,
                phone           TEXT NOT NULL,
                email           TEXT NOT NULL,
                referral_source TEXT NOT NULL,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        cur.execute("""
            ALTER TABLE events_events
            ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT FALSE;
        """)
        cur.execute("""
            ALTER TABLE events_events
            ADD COLUMN IF NOT EXISTS flyer_url TEXT;
        """)
        con.commit()
        cur.close()
        con.close()
        log.info("events tables ready")
    except Exception as e:
        log.error(f"init_events_db failed: {e}")


# ── Auto-archive ───────────────────────────────────────────────────────

def auto_archive_past_events():
    """Archive events whose event_date was more than 2 days ago. Runs nightly."""
    if not DATABASE_URL:
        return
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("""
            UPDATE events_events
            SET archived = TRUE, active = FALSE
            WHERE archived = FALSE
              AND event_date < NOW() - INTERVAL '2 days'
        """)
        count = cur.rowcount
        con.commit()
        cur.close()
        con.close()
        if count:
            log.info(f"Auto-archived {count} past event(s)")
    except Exception as e:
        log.error(f"auto_archive_past_events failed: {e}")


def setup_events_scheduler(scheduler):
    """Add the nightly auto-archive job to the shared APScheduler instance."""
    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        auto_archive_past_events,
        CronTrigger(hour=8, minute=0),  # 2am MT (UTC-6)
        id="events_auto_archive",
        replace_existing=True,
    )


# ── Auth ───────────────────────────────────────────────────────────────

def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="ADMIN_PASSWORD not configured")
    ok = (
        secrets.compare_digest(credentials.username.encode(), b"admin")
        and secrets.compare_digest(credentials.password.encode(), ADMIN_PASSWORD.encode())
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ── Email ──────────────────────────────────────────────────────────────

def send_registration_email(event_name: str, reg: dict):
    if not GMAIL_PASSWORD:
        log.warning("GMAIL_APP_PASSWORD not set — registration email not sent")
        return
    try:
        # ── Internal notification to the business ──────────────────
        internal_body = (
            f"New registration for: {event_name}\n\n"
            f"Full Name:       {reg['full_name']}\n"
            f"Date of Birth:   {reg['dob']}\n"
            f"Phone:           {reg['phone']}\n"
            f"Email:           {reg['email']}\n"
            f"Referral Source: {reg['referral_source']}\n"
            f"Registered At:   {reg.get('created_at', 'now')}\n"
        )
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"New Registration: {event_name}"
        msg["From"]    = GMAIL_USER
        msg["To"]      = GMAIL_USER
        msg.attach(MIMEText(internal_body, "plain"))

        # ── Confirmation email to the registrant ───────────────────
        first_name = reg['full_name'].split()[0]
        confirm_html = f"""
<html><body style="font-family:Georgia,serif;background:#fdf8f9;padding:0;margin:0;">
<div style="max-width:560px;margin:0 auto;background:#fff;border-top:4px solid #c9a96e;">
  <div style="background:linear-gradient(135deg,#2a0d18,#3d1428);padding:40px 36px;text-align:center;">
    <p style="font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#c9a96e;margin:0 0 12px;">Nursify Aesthetics &amp; Wellness</p>
    <h1 style="font-size:28px;font-weight:300;color:#fdf8f9;margin:0;line-height:1.3;">You&rsquo;re <em>Registered!</em></h1>
  </div>
  <div style="padding:36px;">
    <p style="font-size:15px;color:#3d1428;margin:0 0 16px;">Hi {first_name},</p>
    <p style="font-size:14px;color:#4a2535;line-height:1.7;margin:0 0 24px;">
      Thank you for registering for <strong>{event_name}</strong>. We&rsquo;re so excited to have you join us!
    </p>
    <div style="background:#fdf8f9;border-left:3px solid #c9a96e;padding:16px 20px;margin:0 0 24px;border-radius:2px;">
      <p style="font-size:12px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:#c9a96e;margin:0 0 8px;">Your Registration Details</p>
      <p style="font-size:13px;color:#1a0a10;margin:0;line-height:1.8;">
        Name: {reg['full_name']}<br>
        Event: {event_name}<br>
        Location: 5500 San Mateo Blvd NE, Suite 102, Albuquerque, NM 87109
      </p>
    </div>
    <p style="font-size:13px;color:#4a2535;line-height:1.7;margin:0 0 24px;">
      If you have any questions before the event, please don&rsquo;t hesitate to reach out &mdash;
      we&rsquo;re just a call or text away.
    </p>
    <div style="text-align:center;margin:28px 0;">
      <a href="tel:+15055007900" style="display:inline-block;padding:13px 28px;background:linear-gradient(135deg,#d4538f,#ff69b4);color:#fff;text-decoration:none;font-size:12px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;border-radius:4px;">
        Call or Text (505) 500-7900
      </a>
    </div>
    <p style="font-size:12px;color:#a08090;text-align:center;margin:0;">
      Nursify Aesthetics &amp; Wellness &nbsp;&middot;&nbsp; 5500 San Mateo Blvd NE, Suite 102 &nbsp;&middot;&nbsp; Albuquerque, NM 87109
    </p>
  </div>
</div>
</body></html>
"""
        confirm_msg = MIMEMultipart("alternative")
        confirm_msg["Subject"] = f"You're registered — {event_name}"
        confirm_msg["From"]    = f"Nursify Aesthetics & Wellness <{GMAIL_USER}>"
        confirm_msg["To"]      = reg['email']
        confirm_msg.attach(MIMEText(confirm_html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
            server.sendmail(GMAIL_USER, reg['email'], confirm_msg.as_string())

        log.info(f"Registration emails sent for {event_name} to business + {reg['email']}")
    except Exception as e:
        log.error(f"Registration email failed: {e}")


# ── Pydantic models ────────────────────────────────────────────────────

class RegistrationIn(BaseModel):
    full_name:       str
    dob:             str   # YYYY-MM-DD
    phone:           str
    email:           EmailStr
    referral_source: str


class EventCreate(BaseModel):
    name:                  str
    event_date:            str   # ISO 8601 with tz
    registration_deadline: str
    description:           Optional[str] = None
    medical_clearance_note: Optional[str] = None
    flyer_url:             Optional[str] = None
    active:                bool = True


class EventPatch(BaseModel):
    name:                  Optional[str] = None
    event_date:            Optional[str] = None
    registration_deadline: Optional[str] = None
    description:           Optional[str] = None
    medical_clearance_note: Optional[str] = None
    flyer_url:             Optional[str] = None
    active:                Optional[bool] = None


# ── Public endpoints ───────────────────────────────────────────────────

@router.get("/active")
def list_active_events():
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        con = get_db()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, name, event_date, registration_deadline,
                   description, medical_clearance_note, flyer_url
            FROM events_events
            WHERE active = TRUE AND archived = FALSE
            ORDER BY event_date ASC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); con.close()
        for r in rows:
            for k in ("event_date", "registration_deadline", "created_at"):
                if k in r and r[k] is not None:
                    r[k] = r[k].isoformat()
        return JSONResponse({"events": rows})
    except Exception as e:
        log.error(f"list_active_events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/form", response_class=HTMLResponse)
def serve_form():
    path = os.path.join(os.path.dirname(__file__), "events_form.html")
    with open(path, "r") as f:
        return HTMLResponse(content=f.read())


@router.get("/{event_id}")
def get_event(event_id: str):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        con = get_db()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, name, event_date, registration_deadline,
                   description, medical_clearance_note, flyer_url, active
            FROM events_events WHERE id = %s
        """, (event_id,))
        row = cur.fetchone()
        cur.close(); con.close()
        if not row:
            raise HTTPException(status_code=404, detail="Event not found")
        r = dict(row)
        for k in ("event_date", "registration_deadline"):
            if r.get(k):
                r[k] = r[k].isoformat()
        return JSONResponse(r)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"get_event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{event_id}/register")
def register(event_id: str, body: RegistrationIn, background_tasks: BackgroundTasks):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        con = get_db()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Verify event exists and is accepting registrations
        cur.execute("""
            SELECT name, active, registration_deadline
            FROM events_events WHERE id = %s
        """, (event_id,))
        ev = cur.fetchone()
        if not ev:
            cur.close(); con.close()
            raise HTTPException(status_code=404, detail="Event not found")
        if not ev["active"]:
            cur.close(); con.close()
            raise HTTPException(status_code=400, detail="Event is no longer accepting registrations")
        if datetime.now(tz=ev["registration_deadline"].tzinfo) > ev["registration_deadline"]:
            cur.close(); con.close()
            raise HTTPException(status_code=400, detail="Registration deadline has passed")

        cur.execute("""
            INSERT INTO events_registrations
                (event_id, full_name, dob, phone, email, referral_source)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
        """, (
            event_id,
            body.full_name,
            body.dob,
            body.phone,
            body.email,
            body.referral_source,
        ))
        new_row = dict(cur.fetchone())
        con.commit()
        cur.close(); con.close()

        background_tasks.add_task(send_registration_email, ev["name"], {
            "full_name":       body.full_name,
            "dob":             body.dob,
            "phone":           body.phone,
            "email":           body.email,
            "referral_source": body.referral_source,
            "created_at":      new_row["created_at"].isoformat(),
        })

        return JSONResponse({
            "success":    True,
            "id":         str(new_row["id"]),
            "event_name": ev["name"],
            "message":    "Registration confirmed!",
        })
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"register: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Admin endpoints ────────────────────────────────────────────────────

@router.get("/admin/ui", response_class=HTMLResponse)
def admin_ui():
    path = os.path.join(os.path.dirname(__file__), "events_admin.html")
    with open(path, "r") as f:
        return HTMLResponse(content=f.read())


@router.get("/admin/list")
def admin_list_events(
    include_archived: bool = Query(False),
    _: str = Depends(require_admin),
):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        con = get_db()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        where = "" if include_archived else "WHERE e.archived = FALSE"
        cur.execute(f"""
            SELECT e.id, e.name, e.event_date, e.registration_deadline,
                   e.description, e.medical_clearance_note, e.active,
                   e.archived, e.created_at,
                   COUNT(r.id) AS registration_count
            FROM events_events e
            LEFT JOIN events_registrations r ON r.event_id = e.id
            {where}
            GROUP BY e.id
            ORDER BY e.event_date DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); con.close()
        for r in rows:
            for k in ("event_date", "registration_deadline", "created_at"):
                if r.get(k):
                    r[k] = r[k].isoformat()
        return JSONResponse({"events": rows})
    except Exception as e:
        log.error(f"admin_list_events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/{event_id}/archive")
def admin_archive_event(event_id: str, _: str = Depends(require_admin)):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute(
            "UPDATE events_events SET archived = TRUE, active = FALSE WHERE id = %s",
            (event_id,),
        )
        if cur.rowcount == 0:
            cur.close(); con.close()
            raise HTTPException(status_code=404, detail="Event not found")
        con.commit()
        cur.close(); con.close()
        return JSONResponse({"success": True, "id": event_id})
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"admin_archive_event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/create")
def admin_create_event(body: EventCreate, _: str = Depends(require_admin)):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        con = get_db()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            INSERT INTO events_events
                (name, event_date, registration_deadline, description,
                 medical_clearance_note, flyer_url, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, name, event_date, registration_deadline, active, created_at
        """, (
            body.name,
            body.event_date,
            body.registration_deadline,
            body.description,
            body.medical_clearance_note,
            body.flyer_url,
            body.active,
        ))
        row = dict(cur.fetchone())
        con.commit()
        cur.close(); con.close()
        for k in ("event_date", "registration_deadline", "created_at"):
            if row.get(k):
                row[k] = row[k].isoformat()
        return JSONResponse(row, status_code=201)
    except Exception as e:
        log.error(f"admin_create_event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/admin/{event_id}")
def admin_patch_event(event_id: str, body: EventPatch, _: str = Depends(require_admin)):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        con = get_db()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [event_id]
        cur.execute(
            f"UPDATE events_events SET {set_clause} WHERE id = %s RETURNING id",
            values,
        )
        if cur.rowcount == 0:
            cur.close(); con.close()
            raise HTTPException(status_code=404, detail="Event not found")
        con.commit()
        cur.close(); con.close()
        return JSONResponse({"success": True, "id": event_id})
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"admin_patch_event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/{event_id}/registrations")
def admin_list_registrations(
    event_id: str,
    format: Optional[str] = Query(None),
    _: str = Depends(require_admin),
):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        con = get_db()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT name FROM events_events WHERE id = %s", (event_id,))
        ev = cur.fetchone()
        if not ev:
            cur.close(); con.close()
            raise HTTPException(status_code=404, detail="Event not found")

        cur.execute("""
            SELECT id, full_name, dob, phone, email, referral_source, created_at
            FROM events_registrations
            WHERE event_id = %s
            ORDER BY created_at ASC
        """, (event_id,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close(); con.close()

        for r in rows:
            for k in ("created_at",):
                if r.get(k):
                    r[k] = r[k].isoformat()
            if r.get("dob"):
                r["dob"] = r["dob"].isoformat()

        if format == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=["id", "full_name", "dob", "phone", "email",
                            "referral_source", "created_at"],
            )
            writer.writeheader()
            writer.writerows(rows)
            output.seek(0)
            filename = f"registrations_{event_id}.csv"
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        return JSONResponse({"registrations": rows, "count": len(rows)})
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"admin_list_registrations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/registrations/{registration_id}")
def admin_delete_registration(registration_id: str, _: str = Depends(require_admin)):
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("DELETE FROM events_registrations WHERE id = %s", (registration_id,))
        if cur.rowcount == 0:
            cur.close(); con.close()
            raise HTTPException(status_code=404, detail="Registration not found")
        con.commit()
        cur.close(); con.close()
        return JSONResponse({"success": True, "deleted_id": registration_id})
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"admin_delete_registration: {e}")
        raise HTTPException(status_code=500, detail=str(e))

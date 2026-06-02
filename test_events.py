"""
pytest suite for the events router.

Run: pytest test_events.py -v

Uses FastAPI's TestClient with the full app, patching out psycopg2 and
smtplib so no live DB or SMTP server is needed.
"""

import json
import uuid
from base64 import b64encode
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── App setup ─────────────────────────────────────────────────────────
# Must patch env vars before importing chat (which imports events)
import os
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test")
os.environ.setdefault("ADMIN_PASSWORD", "testpass")

from chat import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=True)


# ── Helpers ───────────────────────────────────────────────────────────

def auth_header(password="testpass"):
    token = b64encode(f"admin:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


SAMPLE_EVENT_ID = str(uuid.uuid4())
SAMPLE_REG_ID   = str(uuid.uuid4())

SAMPLE_EVENT = {
    "id":                    SAMPLE_EVENT_ID,
    "name":                  "Nursify Tox Party",
    "event_date":            "2026-06-13T17:00:00-06:00",
    "registration_deadline": "2026-06-11T23:59:00-06:00",
    "description":           None,
    "medical_clearance_note": "Medical clearance required.",
    "active":                True,
}


def make_mock_conn(fetchone=None, fetchall=None, rowcount=1):
    """Return a mock psycopg2 connection whose cursor returns given data."""
    cur = MagicMock()
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall or []
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


# ── Public: GET /events/active ────────────────────────────────────────

def test_active_events_returns_list():
    conn, cur = make_mock_conn(fetchall=[
        (SAMPLE_EVENT_ID, "Tox Party", "2026-06-13T17:00:00+00:00",
         "2026-06-11T23:59:00+00:00", None, "Clearance required.", True)
    ])
    # RealDictCursor returns dict-like rows; simulate with dicts
    row = {
        "id": SAMPLE_EVENT_ID, "name": "Tox Party",
        "event_date": _dt("2026-06-13T17:00:00+00:00"),
        "registration_deadline": _dt("2026-06-11T23:59:00+00:00"),
        "description": None, "medical_clearance_note": "Clearance required.",
    }
    cur.fetchall.return_value = [row]

    with patch("events.get_db", return_value=conn):
        resp = client.get("/events/active")

    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert isinstance(data["events"], list)


def test_active_events_no_db_returns_503():
    with patch("events.DATABASE_URL", ""):
        resp = client.get("/events/active")
    assert resp.status_code == 503


# ── Public: GET /events/{id} ──────────────────────────────────────────

def test_get_event_not_found():
    conn, cur = make_mock_conn(fetchone=None)
    with patch("events.get_db", return_value=conn):
        resp = client.get(f"/events/{SAMPLE_EVENT_ID}")
    assert resp.status_code == 404


def test_get_event_found():
    row = {
        "id": SAMPLE_EVENT_ID, "name": "Tox Party",
        "event_date": _dt("2026-06-13T17:00:00+00:00"),
        "registration_deadline": _dt("2099-01-01T00:00:00+00:00"),
        "description": None, "medical_clearance_note": None, "active": True,
    }
    conn, cur = make_mock_conn(fetchone=row)
    with patch("events.get_db", return_value=conn):
        resp = client.get(f"/events/{SAMPLE_EVENT_ID}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Tox Party"


# ── Public: POST /events/{id}/register ───────────────────────────────

VALID_REG_PAYLOAD = {
    "full_name":       "Jane Smith",
    "dob":             "1990-05-15",
    "phone":           "505-555-0100",
    "email":           "jane@example.com",
    "referral_source": "Instagram",
}


def test_register_success():
    import datetime as dt

    ev_row = {
        "name":                  "Tox Party",
        "active":                True,
        "registration_deadline": dt.datetime(2099, 1, 1, tzinfo=dt.timezone.utc),
    }
    new_row = {"id": SAMPLE_REG_ID, "created_at": dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)}

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.side_effect = [ev_row, new_row]

    with patch("events.get_db", return_value=conn), \
         patch("events.send_registration_email"):
        resp = client.post(f"/events/{SAMPLE_EVENT_ID}/register", json=VALID_REG_PAYLOAD)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["event_name"] == "Tox Party"


def test_register_event_not_found():
    conn, cur = make_mock_conn(fetchone=None)
    with patch("events.get_db", return_value=conn):
        resp = client.post(f"/events/{SAMPLE_EVENT_ID}/register", json=VALID_REG_PAYLOAD)
    assert resp.status_code == 404


def test_register_past_deadline():
    import datetime as dt
    ev_row = {
        "name":                  "Tox Party",
        "active":                True,
        "registration_deadline": dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc),
    }
    conn, cur = make_mock_conn(fetchone=ev_row)
    with patch("events.get_db", return_value=conn):
        resp = client.post(f"/events/{SAMPLE_EVENT_ID}/register", json=VALID_REG_PAYLOAD)
    assert resp.status_code == 400
    assert "deadline" in resp.json()["detail"].lower()


def test_register_inactive_event():
    import datetime as dt
    ev_row = {
        "name": "Old Event", "active": False,
        "registration_deadline": dt.datetime(2099, 1, 1, tzinfo=dt.timezone.utc),
    }
    conn, cur = make_mock_conn(fetchone=ev_row)
    with patch("events.get_db", return_value=conn):
        resp = client.post(f"/events/{SAMPLE_EVENT_ID}/register", json=VALID_REG_PAYLOAD)
    assert resp.status_code == 400


def test_register_missing_field():
    payload = {**VALID_REG_PAYLOAD}
    del payload["email"]
    resp = client.post(f"/events/{SAMPLE_EVENT_ID}/register", json=payload)
    assert resp.status_code == 422


# ── Admin: auth ───────────────────────────────────────────────────────

def test_admin_no_auth_returns_401():
    resp = client.get("/events/admin/list")
    assert resp.status_code == 401


def test_admin_wrong_password_returns_401():
    resp = client.get("/events/admin/list", headers=auth_header("wrong"))
    assert resp.status_code == 401


# ── Admin: GET /events/admin/list ─────────────────────────────────────

def test_admin_list_events():
    row = {
        "id": SAMPLE_EVENT_ID, "name": "Tox Party",
        "event_date": _dt("2026-06-13T17:00:00+00:00"),
        "registration_deadline": _dt("2026-06-11T23:59:00+00:00"),
        "description": None, "medical_clearance_note": None,
        "active": True, "created_at": _dt("2026-01-01T00:00:00+00:00"),
        "registration_count": 3,
    }
    conn, cur = make_mock_conn(fetchall=[row])
    with patch("events.get_db", return_value=conn):
        resp = client.get("/events/admin/list", headers=auth_header())
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["registration_count"] == 3


# ── Admin: POST /events/admin/create ─────────────────────────────────

def test_admin_create_event():
    import datetime as dt
    new_row = {
        "id": SAMPLE_EVENT_ID, "name": "New Event",
        "event_date": dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc),
        "registration_deadline": dt.datetime(2026, 6, 29, tzinfo=dt.timezone.utc),
        "active": True,
        "created_at": dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
    }
    conn, cur = make_mock_conn(fetchone=new_row)
    payload = {
        "name": "New Event",
        "event_date": "2026-07-01T17:00:00-06:00",
        "registration_deadline": "2026-06-29T23:59:00-06:00",
    }
    with patch("events.get_db", return_value=conn):
        resp = client.post("/events/admin/create", json=payload, headers=auth_header())
    assert resp.status_code == 201


# ── Admin: PATCH /events/admin/{id} ──────────────────────────────────

def test_admin_patch_event():
    conn, cur = make_mock_conn(fetchone={"id": SAMPLE_EVENT_ID}, rowcount=1)
    with patch("events.get_db", return_value=conn):
        resp = client.patch(
            f"/events/admin/{SAMPLE_EVENT_ID}",
            json={"active": False},
            headers=auth_header(),
        )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_admin_patch_not_found():
    conn, cur = make_mock_conn(fetchone=None, rowcount=0)
    with patch("events.get_db", return_value=conn):
        resp = client.patch(
            f"/events/admin/{SAMPLE_EVENT_ID}",
            json={"active": False},
            headers=auth_header(),
        )
    assert resp.status_code == 404


# ── Admin: GET /events/admin/{id}/registrations ───────────────────────

def test_admin_registrations_list():
    import datetime as dt
    ev_row = {"name": "Tox Party"}
    reg_rows = [{
        "id": SAMPLE_REG_ID, "full_name": "Jane Smith",
        "dob": dt.date(1990, 5, 15), "phone": "505-555-0100",
        "email": "jane@example.com", "referral_source": "Instagram",
        "created_at": dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
    }]
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = ev_row
    cur.fetchall.return_value = reg_rows
    with patch("events.get_db", return_value=conn):
        resp = client.get(
            f"/events/admin/{SAMPLE_EVENT_ID}/registrations",
            headers=auth_header(),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["registrations"][0]["full_name"] == "Jane Smith"


def test_admin_registrations_csv():
    import datetime as dt
    ev_row = {"name": "Tox Party"}
    reg_rows = [{
        "id": SAMPLE_REG_ID, "full_name": "Jane Smith",
        "dob": dt.date(1990, 5, 15), "phone": "505-555-0100",
        "email": "jane@example.com", "referral_source": "Instagram",
        "created_at": dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
    }]
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = ev_row
    cur.fetchall.return_value = reg_rows
    with patch("events.get_db", return_value=conn):
        resp = client.get(
            f"/events/admin/{SAMPLE_EVENT_ID}/registrations?format=csv",
            headers=auth_header(),
        )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "Jane Smith" in resp.text


# ── Admin: DELETE /events/admin/registrations/{id} ────────────────────

def test_admin_delete_registration():
    conn, cur = make_mock_conn(rowcount=1)
    with patch("events.get_db", return_value=conn):
        resp = client.delete(
            f"/events/admin/registrations/{SAMPLE_REG_ID}",
            headers=auth_header(),
        )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_admin_delete_registration_not_found():
    conn, cur = make_mock_conn(rowcount=0)
    with patch("events.get_db", return_value=conn):
        resp = client.delete(
            f"/events/admin/registrations/{SAMPLE_REG_ID}",
            headers=auth_header(),
        )
    assert resp.status_code == 404


# ── Admin: no ADMIN_PASSWORD configured ──────────────────────────────

def test_admin_no_password_env_returns_503():
    with patch("events.ADMIN_PASSWORD", ""):
        resp = client.get("/events/admin/list", headers=auth_header())
    assert resp.status_code == 503


# ── Util ──────────────────────────────────────────────────────────────

def _dt(iso: str):
    """Parse ISO string to aware datetime (used to build mock row dicts)."""
    import datetime as dt
    return dt.datetime.fromisoformat(iso)

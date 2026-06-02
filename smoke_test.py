"""
Smoke test — hits the live Railway deployment.

Usage:
  python smoke_test.py https://your-app.railway.app testpass

The script:
  1. Checks /health
  2. Lists active events
  3. Creates a test event (admin)
  4. Submits a registration
  5. Lists registrations
  6. Downloads CSV
  7. Deletes the test registration
  8. Deactivates the test event
  9. Prints a pass/fail summary
"""

import sys
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

BASE_URL     = (sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000")
ADMIN_PASS   = (sys.argv[2] if len(sys.argv) > 2 else "testpass")

BASIC_AUTH   = base64.b64encode(f"admin:{ADMIN_PASS}".encode()).decode()
HEADERS_AUTH = {"Authorization": f"Basic {BASIC_AUTH}", "Content-Type": "application/json"}
HEADERS_JSON = {"Content-Type": "application/json"}

results = []


def req(method, path, data=None, headers=None, expect=None):
    url  = BASE_URL + path
    body = json.dumps(data).encode() if data else None
    h    = {**(headers or {})}
    r    = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            status  = resp.status
            content = resp.read()
            try:
                payload = json.loads(content)
            except Exception:
                payload = content.decode(errors="replace")
    except urllib.error.HTTPError as e:
        status  = e.code
        content = e.read()
        try:
            payload = json.loads(content)
        except Exception:
            payload = content.decode(errors="replace")

    ok = (status == expect) if expect else (status < 300)
    tag = "PASS" if ok else "FAIL"
    label = f"{method} {path}"
    results.append((tag, label, status))
    print(f"  [{tag}] {label}  →  {status}")
    if not ok:
        print(f"         {payload}")
    return status, payload


print(f"\nSmoke test → {BASE_URL}\n")

# 1. Health check
req("GET", "/health")

# 2. Active events
_, active = req("GET", "/events/active")
existing_ids = [e["id"] for e in (active.get("events") or [])] if isinstance(active, dict) else []

# 3. Create test event (admin)
future_event = datetime.now(timezone.utc) + timedelta(days=30)
future_deadline = datetime.now(timezone.utc) + timedelta(days=28)
_, created = req("POST", "/events/admin/create", data={
    "name": "__smoke_test_event__",
    "event_date": future_event.isoformat(),
    "registration_deadline": future_deadline.isoformat(),
    "active": True,
}, headers=HEADERS_AUTH, expect=201)

event_id = created.get("id") if isinstance(created, dict) else None
if not event_id:
    print("\nCould not create test event — aborting remaining steps.")
    sys.exit(1)
print(f"         event_id = {event_id}")

# 4. Register
_, reg = req("POST", f"/events/{event_id}/register", data={
    "full_name":       "Smoke Test User",
    "dob":             "1990-01-01",
    "phone":           "505-555-0000",
    "email":           "smoke@example.com",
    "referral_source": "Other",
}, headers=HEADERS_JSON)

reg_id = reg.get("id") if isinstance(reg, dict) else None
print(f"         registration_id = {reg_id}")

# 5. List registrations
req("GET", f"/events/admin/{event_id}/registrations", headers=HEADERS_AUTH)

# 6. CSV export
req("GET", f"/events/admin/{event_id}/registrations?format=csv", headers=HEADERS_AUTH)

# 7. Delete test registration
if reg_id:
    req("DELETE", f"/events/admin/registrations/{reg_id}", headers=HEADERS_AUTH)

# 8. Deactivate test event
req("PATCH", f"/events/admin/{event_id}", data={"active": False}, headers=HEADERS_AUTH)

# ── Summary ───────────────────────────────────────────────────────────
passed = sum(1 for t, _, _ in results if t == "PASS")
failed = sum(1 for t, _, _ in results if t == "FAIL")
print(f"\n{'='*44}")
print(f"  {passed} passed  |  {failed} failed  |  {len(results)} total")
print(f"{'='*44}\n")
sys.exit(0 if failed == 0 else 1)

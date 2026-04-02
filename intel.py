"""
Nursify Competitor Intelligence Bot
Scrapes Albuquerque med spa competitors weekly
Sends email briefing + instant alerts via Gmail SMTP
Runs as background scheduler alongside chat.py on Railway
"""

import asyncio
import httpx
import sqlite3
import smtplib
import json
import os
import re
import logging
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import anthropic

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nursify.intel")

# ── Config ─────────────────────────────────────────────────────────────
GMAIL_USER     = os.environ.get("GMAIL_USER", "nursifyaesthetics@gmail.com")
GMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
ALERT_EMAIL    = "tyagi.ramakrishnan@gmail.com"
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
DB_PATH        = "/app/intel.db"

# ── Competitor seed list ───────────────────────────────────────────────
COMPETITORS = [
    {"name": "AlluraDerm MD MedSpa",        "url": "https://alluraderm.com",                    "instagram": "alluraderm"},
    {"name": "Flawless Med Spa",             "url": "https://www.stayflawless.com",              "instagram": "stayflawless_medspa"},
    {"name": "dermani MEDSPA Albuquerque",   "url": "https://dermanimedspa.com/albuquerque-nm",  "instagram": "dermanimedspa"},
    {"name": "Bair Medical Spa",             "url": "https://bairmedspa.com",                    "instagram": "bairmedspa"},
    {"name": "ABQ Medical Spa",              "url": "https://medspaalbuquerque.com",              "instagram": "abqmedspanm"},
    {"name": "Nuyu Med Spa",                 "url": "https://nuyumedspanm.com",                  "instagram": "nuyumedspanm"},
    {"name": "Silhouette Medical Spa",       "url": "https://www.silhouette-medspa.com",         "instagram": "silhouette_medspa"},
    {"name": "Diversions Med Spa",           "url": "https://diversionsmedspa.com",              "instagram": "diversionsmedspa"},
    {"name": "Reverse Medical Spa",          "url": "https://reversemedspa.com",                 "instagram": "reversemedspa"},
    {"name": "About Face Med Spa",           "url": "https://aboutfacemedspa.com",               "instagram": "aboutfacemedspa"},
]

NURSIFY = {
    "name": "Nursify Aesthetics & Wellness",
    "url":  "https://nursifyaesthetics.com",
    "instagram": "nursifyaestheticsllc",
}

TRACKED_KEYWORDS = [
    "botox albuquerque",
    "med spa albuquerque",
    "lip filler albuquerque",
    "medical weight loss albuquerque",
    "daxxify albuquerque",
]

# ── Database ───────────────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            url         TEXT,
            scanned_at  TEXT NOT NULL,
            rating      REAL,
            review_count INTEGER,
            services    TEXT,
            promotions  TEXT,
            pricing     TEXT,
            instagram_followers INTEGER,
            instagram_last_post TEXT,
            running_ads INTEGER DEFAULT 0,
            raw_text    TEXT
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT NOT NULL,
            competitor  TEXT NOT NULL,
            alert_type  TEXT NOT NULL,
            message     TEXT NOT NULL,
            sent        INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS weekly_reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT NOT NULL,
            report_html TEXT NOT NULL,
            report_text TEXT NOT NULL
        );
    """)
    con.commit()
    con.close()
    log.info("Database initialized")

def get_latest_snapshot(name: str) -> dict | None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        SELECT * FROM snapshots WHERE name = ?
        ORDER BY scanned_at DESC LIMIT 1
    """, (name,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    cols = ["id","name","url","scanned_at","rating","review_count",
            "services","promotions","pricing","instagram_followers",
            "instagram_last_post","running_ads","raw_text"]
    return dict(zip(cols, row))

def save_snapshot(data: dict):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO snapshots
        (name,url,scanned_at,rating,review_count,services,promotions,
         pricing,instagram_followers,instagram_last_post,running_ads,raw_text)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data.get("name"), data.get("url"),
        datetime.utcnow().isoformat(),
        data.get("rating"), data.get("review_count"),
        json.dumps(data.get("services", [])),
        json.dumps(data.get("promotions", [])),
        data.get("pricing",""),
        data.get("instagram_followers"),
        data.get("instagram_last_post",""),
        int(data.get("running_ads", False)),
        data.get("raw_text","")[:5000],
    ))
    con.commit()
    con.close()

def save_alert(competitor: str, alert_type: str, message: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO alerts (created_at, competitor, alert_type, message)
        VALUES (?,?,?,?)
    """, (datetime.utcnow().isoformat(), competitor, alert_type, message))
    con.commit()
    con.close()

def get_alerts(days: int = 7) -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    cur.execute("""
        SELECT id, created_at, competitor, alert_type, message
        FROM alerts WHERE created_at > ? ORDER BY created_at DESC
    """, (since,))
    rows = cur.fetchall()
    con.close()
    return [{"id":r[0],"created_at":r[1],"competitor":r[2],
             "alert_type":r[3],"message":r[4]} for r in rows]

def get_all_latest_snapshots() -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        SELECT s.* FROM snapshots s
        INNER JOIN (
            SELECT name, MAX(scanned_at) as max_date
            FROM snapshots GROUP BY name
        ) latest ON s.name = latest.name AND s.scanned_at = latest.max_date
        ORDER BY s.rating DESC
    """)
    rows = cur.fetchall()
    con.close()
    cols = ["id","name","url","scanned_at","rating","review_count",
            "services","promotions","pricing","instagram_followers",
            "instagram_last_post","running_ads","raw_text"]
    return [dict(zip(cols, r)) for r in rows]

# ── Scrapers ───────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

async def scrape_website(url: str) -> dict:
    """Scrape competitor website for pricing, services, promotions."""
    result = {"pricing": "", "services": [], "promotions": [], "raw_text": ""}
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return result
            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "head"]):
                tag.decompose()

            text = soup.get_text(separator=" ", strip=True)
            result["raw_text"] = text[:5000]

            # Extract pricing mentions
            price_pattern = r'\$\d+(?:\.\d{2})?(?:\s*/\s*(?:unit|syringe|session|month|treatment|visit))?'
            prices = re.findall(price_pattern, text, re.IGNORECASE)
            result["pricing"] = ", ".join(list(dict.fromkeys(prices))[:15])

            # Extract services
            service_keywords = [
                "botox","daxxify","xeomin","dysport","filler","juvederm",
                "restylane","microneedling","skinpen","prp","prf","weight loss",
                "semaglutide","tirzepatide","wellness","vitamin","b12","nad",
                "laser","morpheus","coolsculpting","kybella","hydrafacial",
            ]
            found = [k for k in service_keywords if k.lower() in text.lower()]
            result["services"] = found

            # Extract promotions
            promo_patterns = [
                r'(?:special|promo|offer|sale|discount|off|deal|free|complimentary)[^.!?]{0,100}[.!?]',
            ]
            promos = []
            for pattern in promo_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                promos.extend(matches[:3])
            result["promotions"] = promos[:5]

    except Exception as e:
        log.warning(f"Website scrape failed for {url}: {e}")
    return result

async def scrape_instagram(handle: str) -> dict:
    """Scrape public Instagram profile for follower count and last post."""
    result = {"instagram_followers": None, "instagram_last_post": ""}
    if not handle:
        return result
    try:
        url = f"https://www.instagram.com/{handle}/"
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=HEADERS) as client:
            resp = await client.get(url)
            text = resp.text

            # Follower count from meta tags
            follower_match = re.search(r'"edge_followed_by":\{"count":(\d+)\}', text)
            if follower_match:
                result["instagram_followers"] = int(follower_match.group(1))

            # Last post date
            date_match = re.search(r'"taken_at_timestamp":(\d+)', text)
            if date_match:
                ts = int(date_match.group(1))
                result["instagram_last_post"] = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")

    except Exception as e:
        log.warning(f"Instagram scrape failed for {handle}: {e}")
    return result

async def check_google_ads(keyword: str, competitor_name: str) -> bool:
    """Check if competitor is running Google Ads for a keyword."""
    try:
        search_url = f"https://www.google.com/search?q={keyword.replace(' ', '+')}"
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            resp = await client.get(search_url)
            text = resp.text.lower()
            comp_lower = competitor_name.lower().split()[0]
            # Look for sponsored/ad markers near competitor name
            sponsored_idx = [m.start() for m in re.finditer(r'sponsored|paid', text)]
            for idx in sponsored_idx:
                window = text[max(0,idx-200):idx+200]
                if comp_lower in window:
                    return True
    except Exception as e:
        log.warning(f"Google Ads check failed: {e}")
    return False

# ── Diff engine ────────────────────────────────────────────────────────
def detect_changes(prev: dict | None, curr: dict) -> list[dict]:
    """Compare previous and current snapshot, return list of notable changes."""
    if not prev:
        return []

    changes = []
    name = curr["name"]

    # Rating drop
    if prev.get("rating") and curr.get("rating"):
        diff = curr["rating"] - prev["rating"]
        if diff <= -0.3:
            changes.append({
                "type": "rating_drop",
                "message": f"{name} rating dropped from {prev['rating']} to {curr['rating']} ⚠️",
                "urgent": True,
            })
        elif diff >= 0.3:
            changes.append({
                "type": "rating_rise",
                "message": f"{name} rating rose from {prev['rating']} to {curr['rating']}",
                "urgent": False,
            })

    # Review surge
    if prev.get("review_count") and curr.get("review_count"):
        new_reviews = curr["review_count"] - prev["review_count"]
        if new_reviews >= 10:
            changes.append({
                "type": "review_surge",
                "message": f"{name} gained {new_reviews} new reviews this week 📈",
                "urgent": True,
            })

    # New services
    prev_services = set(json.loads(prev.get("services","[]")))
    curr_services = set(json.loads(curr.get("services","[]"))) if isinstance(curr.get("services"), str) else set(curr.get("services",[]))
    new_services = curr_services - prev_services
    if new_services:
        changes.append({
            "type": "new_service",
            "message": f"{name} added new services: {', '.join(new_services)}",
            "urgent": False,
        })

    # New promotions
    prev_promos = set(json.loads(prev.get("promotions","[]")))
    curr_promos = set(curr.get("promotions",[])) if isinstance(curr.get("promotions"), list) else set(json.loads(curr.get("promotions","[]")))
    new_promos = curr_promos - prev_promos
    if new_promos:
        changes.append({
            "type": "new_promotion",
            "message": f"{name} is running new promotions: {list(new_promos)[0][:100]}",
            "urgent": False,
        })

    # Google Ads started
    if not prev.get("running_ads") and curr.get("running_ads"):
        changes.append({
            "type": "ads_started",
            "message": f"{name} started running Google Ads 🎯",
            "urgent": True,
        })

    return changes

# ── Claude insights ────────────────────────────────────────────────────
async def generate_insights(snapshots: list[dict], alerts: list[dict], nursify_snapshot: dict | None) -> str:
    """Ask Claude to generate actionable insights from the week's data."""
    if not ANTHROPIC_KEY:
        return "Claude insights unavailable — ANTHROPIC_API_KEY not set."

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    snapshot_summary = []
    for s in snapshots[:10]:
        snapshot_summary.append(
            f"- {s['name']}: {s.get('rating','?')}★ ({s.get('review_count','?')} reviews), "
            f"services: {s.get('services','[]')}, promotions: {s.get('promotions','[]')}, "
            f"pricing: {s.get('pricing','unknown')[:100]}, ads: {s.get('running_ads',0)}"
        )

    alert_summary = [f"- {a['alert_type']}: {a['message']}" for a in alerts[:10]]

    prompt = f"""You are a business intelligence analyst for Nursify Aesthetics & Wellness, a nurse-led med spa in Albuquerque, NM.

Nursify offers: Botox ($12/unit), DAXXIFY ($10/unit, most popular), dermal fillers, microneedling, PRF hair restoration, wellness injections, medical weight loss (semaglutide/tirzepatide), and in-home concierge services.

COMPETITOR SNAPSHOTS THIS WEEK:
{chr(10).join(snapshot_summary)}

ALERTS THIS WEEK:
{chr(10).join(alert_summary) if alert_summary else "No major alerts"}

NURSIFY CURRENT STATUS:
{f"Rating: {nursify_snapshot.get('rating')}★, Reviews: {nursify_snapshot.get('review_count')}" if nursify_snapshot else "No Nursify data yet"}

Generate a concise intelligence briefing with:
1. The 2-3 most important things Thanisha should know this week
2. One specific competitive opportunity she can act on immediately
3. One suggested Instagram post or promotion based on what competitors are doing
4. One thing Nursify is doing better than everyone else (reinforce the strength)

Keep it under 200 words. Plain text, no markdown, warm but professional tone."""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        log.error(f"Claude insights failed: {e}")
        return "Claude insights unavailable this week."

# ── Email sender ───────────────────────────────────────────────────────
def send_email(subject: str, html_body: str, text_body: str):
    """Send email via Gmail SMTP."""
    if not GMAIL_PASSWORD:
        log.warning("GMAIL_APP_PASSWORD not set — email not sent")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_USER
        msg["To"]      = ALERT_EMAIL
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, ALERT_EMAIL, msg.as_string())
        log.info(f"Email sent: {subject}")
        return True
    except Exception as e:
        log.error(f"Email send failed: {e}")
        return False

def build_weekly_email(snapshots: list[dict], alerts: list[dict], insights: str) -> tuple[str, str]:
    """Build weekly HTML + text email."""
    week = datetime.utcnow().strftime("%B %d, %Y")

    # Sort by rating desc
    sorted_snaps = sorted(snapshots, key=lambda x: x.get("rating") or 0, reverse=True)

    rows_html = ""
    for s in sorted_snaps:
        rating = s.get("rating") or "N/A"
        reviews = s.get("review_count") or "N/A"
        ads = "🎯 Running ads" if s.get("running_ads") else ""
        rows_html += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #f0e8ec;">{s['name']}</td>
            <td style="padding:8px;border-bottom:1px solid #f0e8ec;text-align:center;">{rating}★</td>
            <td style="padding:8px;border-bottom:1px solid #f0e8ec;text-align:center;">{reviews}</td>
            <td style="padding:8px;border-bottom:1px solid #f0e8ec;font-size:12px;color:#888;">{s.get('pricing','')[:60]}</td>
            <td style="padding:8px;border-bottom:1px solid #f0e8ec;font-size:12px;color:#c9a96e;">{ads}</td>
        </tr>"""

    alerts_html = ""
    for a in alerts:
        color = "#e74c3c" if a["alert_type"] in ["rating_drop","ads_started","review_surge"] else "#c9a96e"
        alerts_html += f'<li style="margin:6px 0;color:{color};">{a["message"]}</li>'
    if not alerts_html:
        alerts_html = '<li style="color:#888;">No major alerts this week</li>'

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Georgia,serif;max-width:700px;margin:0 auto;background:#fdf8f9;padding:20px;">

  <div style="background:linear-gradient(135deg,#3d1428,#5a1e35);padding:30px;border-radius:12px;text-align:center;margin-bottom:24px;">
    <h1 style="color:#c9a96e;margin:0;font-size:22px;letter-spacing:0.1em;">NURSIFY INTELLIGENCE</h1>
    <p style="color:rgba(253,248,249,0.7);margin:8px 0 0;font-size:14px;">Weekly Competitor Briefing — {week}</p>
  </div>

  <div style="background:white;border-radius:8px;padding:20px;margin-bottom:16px;border:1px solid #f0e8ec;">
    <h2 style="color:#3d1428;font-size:16px;margin:0 0 16px;">📊 Market Snapshot</h2>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#fdf8f9;">
          <th style="padding:8px;text-align:left;color:#888;font-weight:500;">Business</th>
          <th style="padding:8px;text-align:center;color:#888;font-weight:500;">Rating</th>
          <th style="padding:8px;text-align:center;color:#888;font-weight:500;">Reviews</th>
          <th style="padding:8px;color:#888;font-weight:500;">Pricing Intel</th>
          <th style="padding:8px;color:#888;font-weight:500;">Ads</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>

  <div style="background:white;border-radius:8px;padding:20px;margin-bottom:16px;border:1px solid #f0e8ec;">
    <h2 style="color:#3d1428;font-size:16px;margin:0 0 12px;">🔔 Alerts This Week</h2>
    <ul style="margin:0;padding-left:20px;">{alerts_html}</ul>
  </div>

  <div style="background:white;border-radius:8px;padding:20px;margin-bottom:16px;border:1px solid #f0e8ec;">
    <h2 style="color:#3d1428;font-size:16px;margin:0 0 12px;">🧠 Claude's Take</h2>
    <p style="color:#444;line-height:1.7;font-size:14px;margin:0;">{insights.replace(chr(10),'<br>')}</p>
  </div>

  <div style="text-align:center;padding:16px;">
    <a href="https://nursifyaesthetics.com/intel/" style="background:#3d1428;color:#c9a96e;padding:12px 28px;border-radius:20px;text-decoration:none;font-size:13px;letter-spacing:0.1em;">View Full Dashboard</a>
  </div>

  <p style="text-align:center;color:#bbb;font-size:11px;margin-top:20px;">Nursify Intelligence Bot — nursifyaesthetics.com</p>

</body>
</html>"""

    text = f"""NURSIFY INTELLIGENCE — {week}

MARKET SNAPSHOT
{"="*50}
"""
    for s in sorted_snaps:
        text += f"{s['name']}: {s.get('rating','?')}★ ({s.get('review_count','?')} reviews)\n"
        if s.get("pricing"):
            text += f"  Pricing: {s['pricing'][:80]}\n"
        if s.get("running_ads"):
            text += "  ⚠️ Running Google Ads\n"

    text += f"\nALERTS THIS WEEK\n{'='*50}\n"
    for a in alerts:
        text += f"• {a['message']}\n"

    text += f"\nCLAUDE'S TAKE\n{'='*50}\n{insights}\n"
    text += f"\nView dashboard: https://nursifyaesthetics.com/intel/"

    return html, text

def build_alert_email(changes: list[dict], competitor: str) -> tuple[str, str]:
    """Build instant alert email for urgent changes."""
    items_html = "".join([
        f'<li style="margin:8px 0;padding:8px;background:#fff5f5;border-left:3px solid #e74c3c;font-size:14px;">{c["message"]}</li>'
        for c in changes if c.get("urgent")
    ])

    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Georgia,serif;max-width:600px;margin:0 auto;padding:20px;">
  <div style="background:#3d1428;padding:20px;border-radius:8px;text-align:center;margin-bottom:20px;">
    <h1 style="color:#c9a96e;margin:0;font-size:18px;">⚡ NURSIFY INTEL ALERT</h1>
  </div>
  <div style="background:white;padding:20px;border-radius:8px;border:1px solid #f0e8ec;">
    <p style="color:#666;margin:0 0 12px;font-size:14px;">Significant change detected for <strong>{competitor}</strong>:</p>
    <ul style="margin:0;padding-left:0;list-style:none;">{items_html}</ul>
  </div>
  <p style="text-align:center;margin-top:16px;">
    <a href="https://nursifyaesthetics.com/intel/" style="background:#3d1428;color:#c9a96e;padding:10px 24px;border-radius:20px;text-decoration:none;font-size:13px;">View Dashboard</a>
  </p>
</body>
</html>"""

    text = f"NURSIFY INTEL ALERT — {competitor}\n\n"
    for c in changes:
        if c.get("urgent"):
            text += f"• {c['message']}\n"
    text += f"\nView dashboard: https://nursifyaesthetics.com/intel/"

    return html, text

# ── Main scan ──────────────────────────────────────────────────────────
async def scan_competitor(comp: dict) -> dict | None:
    """Scrape a single competitor and return snapshot dict."""
    log.info(f"Scanning {comp['name']}...")
    try:
        web_data = await scrape_website(comp["url"])
        ig_data  = await scrape_instagram(comp.get("instagram",""))

        # Check Google Ads for first keyword only (avoid rate limiting)
        running_ads = False
        if TRACKED_KEYWORDS:
            running_ads = await check_google_ads(TRACKED_KEYWORDS[0], comp["name"])

        snapshot = {
            "name":                 comp["name"],
            "url":                  comp["url"],
            "rating":               None,  # Would need SerpAPI for live Google rating
            "review_count":         None,  # Same — upgrade path
            "services":             web_data.get("services", []),
            "promotions":           web_data.get("promotions", []),
            "pricing":              web_data.get("pricing", ""),
            "instagram_followers":  ig_data.get("instagram_followers"),
            "instagram_last_post":  ig_data.get("instagram_last_post",""),
            "running_ads":          running_ads,
            "raw_text":             web_data.get("raw_text",""),
        }
        return snapshot
    except Exception as e:
        log.error(f"Failed to scan {comp['name']}: {e}")
        return None

async def run_full_scan():
    """Run full competitor scan, detect changes, send alerts + weekly report."""
    log.info("Starting full competitor scan...")
    init_db()

    all_snapshots = []
    urgent_changes = []

    for comp in COMPETITORS:
        snapshot = await scan_competitor(comp)
        if not snapshot:
            continue

        # Get previous snapshot for diff
        prev = get_latest_snapshot(comp["name"])

        # Save new snapshot
        save_snapshot(snapshot)
        all_snapshots.append(snapshot)

        # Detect changes
        changes = detect_changes(prev, snapshot)
        for change in changes:
            save_alert(comp["name"], change["type"], change["message"])
            if change.get("urgent"):
                urgent_changes.append((comp["name"], change))

        # Send instant alert for urgent changes
        if any(c.get("urgent") for c in changes):
            urgent = [c for c in changes if c.get("urgent")]
            html, text = build_alert_email(urgent, comp["name"])
            send_email(
                f"⚡ Nursify Intel Alert — {comp['name']}",
                html, text
            )

        # Polite delay between requests
        await asyncio.sleep(2)

    # Also scan Nursify itself for self-awareness
    nursify_snapshot = await scan_competitor(NURSIFY)
    if nursify_snapshot:
        save_snapshot(nursify_snapshot)

    # Generate Claude insights
    recent_alerts = get_alerts(days=7)
    insights = await generate_insights(all_snapshots, recent_alerts, nursify_snapshot)

    # Build and send weekly report
    html, text = build_weekly_email(all_snapshots, recent_alerts, insights)
    send_email(
        f"🕵️ Nursify Intel — Week of {datetime.utcnow().strftime('%B %d')}",
        html, text
    )

    log.info(f"Scan complete. {len(all_snapshots)} competitors scanned, {len(urgent_changes)} urgent alerts.")
    return {
        "scanned": len(all_snapshots),
        "alerts": len(recent_alerts),
        "urgent": len(urgent_changes),
    }

# ── FastAPI routes (imported by main app) ─────────────────────────────
from fastapi import APIRouter, BackgroundTasks

intel_router = APIRouter(prefix="/intel", tags=["intelligence"])

@intel_router.get("/health")
async def intel_health():
    return {"status": "ok", "scheduler": "running"}

@intel_router.post("/scan")
async def trigger_scan(background_tasks: BackgroundTasks):
    """Manually trigger a full scan."""
    background_tasks.add_task(run_full_scan)
    return {"status": "scan started"}

@intel_router.get("/dashboard")
async def dashboard_data():
    """Return all data needed for WordPress dashboard."""
    init_db()
    snapshots = get_all_latest_snapshots()
    alerts    = get_alerts(days=30)

    # Parse JSON fields
    for s in snapshots:
        try:
            s["services"]   = json.loads(s["services"])   if isinstance(s["services"], str)   else s["services"]
            s["promotions"] = json.loads(s["promotions"]) if isinstance(s["promotions"], str) else s["promotions"]
        except Exception:
            pass

    return {
        "snapshots":      snapshots,
        "alerts":         alerts,
        "last_scan":      snapshots[0]["scanned_at"] if snapshots else None,
        "competitor_count": len(snapshots),
    }

@intel_router.get("/competitors")
async def get_competitors():
    return {"competitors": COMPETITORS}

# ── Scheduler setup ───────────────────────────────────────────────────
def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # Every Monday at 8am UTC (Mountain time is UTC-6/7)
    scheduler.add_job(
        run_full_scan,
        CronTrigger(day_of_week="mon", hour=14, minute=0),  # 8am MT
        id="weekly_scan",
        replace_existing=True,
    )
    return scheduler

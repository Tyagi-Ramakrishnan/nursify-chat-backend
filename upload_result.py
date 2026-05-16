"""
Nursify Photo Upload — R2 + Postgres
--------------------------------------
Stores images in Cloudflare R2, metadata in Postgres.
Completely bypasses WordPress media library.

Railway env vars:
    R2_ACCOUNT_ID       = a4891e5433d5e9ff4d8221e00109a8f4
    R2_ACCESS_KEY_ID    = 960960e99d2c4d7138764ba81f2a92d0
    R2_SECRET_ACCESS_KEY= 940dda2a2bd37a93560c60eec474755b485f5b69a2b6f6baceac4eaf4cbc44b5
    R2_BUCKET_NAME      = nursify-photos
    R2_PUBLIC_URL       = https://pub-bae390525bb94574b8b5fba083e5b624.r2.dev
    UPLOAD_SECRET       = nursify-upload-2025
    DATABASE_URL        = (your Railway Postgres URL)
"""

import functools
import io
import os
import uuid
import logging
import boto3
import httpx
import psycopg2
import psycopg2.extras
from PIL import Image

from botocore.config import Config
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse, Response, HTMLResponse
from typing import Optional

log = logging.getLogger("nursify.upload")

# ── Config ─────────────────────────────────────────────────────────────────────
R2_ACCOUNT_ID        = os.environ.get("R2_ACCOUNT_ID",        "a4891e5433d5e9ff4d8221e00109a8f4")
R2_ACCESS_KEY_ID     = os.environ.get("R2_ACCESS_KEY_ID",     "960960e99d2c4d7138764ba81f2a92d0")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME       = os.environ.get("R2_BUCKET_NAME",       "nursify-photos")
R2_PUBLIC_URL        = os.environ.get("R2_PUBLIC_URL",        "https://pub-bae390525bb94574b8b5fba083e5b624.r2.dev")
R2_ENDPOINT          = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
UPLOAD_SECRET        = os.environ.get("UPLOAD_SECRET",        "nursify-upload-2025")
DATABASE_URL         = os.environ.get("DATABASE_URL",         "")

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 8 * 1024 * 1024  # 8MB

upload_router = APIRouter(prefix="/upload", tags=["upload"])


# ── R2 client ──────────────────────────────────────────────────────────────────
def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


# ── Postgres ───────────────────────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_photos_table():
    """Create photos table if it doesn't exist."""
    if not DATABASE_URL:
        return
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS nursify_photos (
                id            SERIAL PRIMARY KEY,
                title         TEXT NOT NULL,
                src           TEXT NOT NULL,
                instagram_url TEXT NOT NULL,
                procedure     TEXT NOT NULL,
                show_on_home  BOOLEAN DEFAULT TRUE,
                uploaded_at   TIMESTAMP DEFAULT NOW(),
                source        TEXT DEFAULT 'upload_portal'
            );
        """)
        con.commit()
        cur.close()
        con.close()
        log.info("nursify_photos table ready")
    except Exception as e:
        log.error(f"DB init failed: {e}")


# ── Health ─────────────────────────────────────────────────────────────────────
@upload_router.get("/health")
async def upload_health():
    return {
        "status":      "ok",
        "r2_ready":    bool(R2_SECRET_ACCESS_KEY),
        "db_ready":    bool(DATABASE_URL),
        "secret_set":  bool(UPLOAD_SECRET),
        "public_url":  R2_PUBLIC_URL,
    }


# ── GET /admin — standalone photo manager UI ──────────────────────────────────
@upload_router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return HTMLResponse(content=_ADMIN_HTML)


_ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nursify — Photo Manager</title>
<meta name="robots" content="noindex, nofollow">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400&family=Montserrat:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --pink: #ff69b4; --pink-light: #ffb6c1;
  --text: #2a2a2a; --muted: #888; --border: #f0d9e8; --white: #fff;
  --radius: 12px; --shadow: 0 4px 24px rgba(255,105,180,0.12);
}
body {
  font-family: 'Montserrat', sans-serif;
  background: linear-gradient(160deg,#fff5fa 0%,#fff 60%);
  min-height: 100vh; color: var(--text);
}

/* ── Login ── */
#login-screen {
  display: flex; align-items: center; justify-content: center;
  min-height: 100vh; padding: 24px 16px;
}
.login-wrap { width: 100%; max-width: 400px; }
.login-header { text-align: center; margin-bottom: 32px; }
.login-header h1 { font-family: 'Cormorant Garamond', serif; font-size: 28px; font-weight: 400; }
.login-header p { font-size: 11px; font-weight: 500; letter-spacing: 0.12em; text-transform: uppercase; color: var(--pink); margin-top: 6px; }
.card { background: var(--white); border-radius: var(--radius); box-shadow: var(--shadow); border: 1px solid var(--border); padding: 32px 28px; }
.field { margin-bottom: 20px; }
.field label { display: block; font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); margin-bottom: 7px; }
.field input { width: 100%; padding: 12px 14px; font-family: 'Montserrat', sans-serif; font-size: 14px; border: 1.5px solid var(--border); border-radius: 8px; background: #fafafa; color: var(--text); }
.field input:focus { outline: none; border-color: var(--pink); box-shadow: 0 0 0 3px rgba(255,105,180,.12); background: var(--white); }
.btn-primary { width: 100%; padding: 14px; background: linear-gradient(135deg,var(--pink) 0%,var(--pink-light) 100%); color: var(--white); border: none; border-radius: 8px; font-family: 'Montserrat', sans-serif; font-size: 13px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; cursor: pointer; }
.btn-primary:hover { opacity: .9; }
.alert-error { padding: 10px 14px; background: #fff0f0; color: #c0392b; border: 1px solid #ffc9c9; border-radius: 8px; font-size: 13px; margin-bottom: 16px; }

/* ── Admin ── */
#admin-screen { display: none; padding: 32px 24px 60px; max-width: 1200px; margin: 0 auto; }
.admin-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
.admin-header h1 { font-family: 'Cormorant Garamond', serif; font-size: 26px; font-weight: 400; }
.admin-meta { display: flex; align-items: center; gap: 16px; }
#photo-count { font-size: 12px; color: var(--muted); }
.btn-logout { font-size: 11px; font-weight: 600; color: var(--muted); background: none; border: 1px solid var(--border); border-radius: 6px; padding: 6px 14px; cursor: pointer; font-family: 'Montserrat', sans-serif; }
.btn-logout:hover { border-color: var(--pink); color: var(--pink); }
.filter-bar { margin-bottom: 20px; }
.filter-bar select { padding: 10px 14px; font-family: 'Montserrat', sans-serif; font-size: 12px; border: 1.5px solid var(--border); border-radius: 8px; background: var(--white); color: var(--text); cursor: pointer; }
.photo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }
.photo-card { background: var(--white); border-radius: 10px; border: 1px solid var(--border); overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,.05); transition: opacity .3s ease; }
.photo-card img { width: 100%; height: 160px; object-fit: cover; display: block; background: #f8f0f5; }
.photo-card-body { padding: 10px 12px 12px; }
.photo-card-title { font-size: 11px; font-weight: 500; line-height: 1.4; margin-bottom: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.photo-card-meta { display: flex; align-items: center; justify-content: space-between; gap: 4px; }
.procedure-badge { font-size: 9px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--pink); background: rgba(255,105,180,.08); border: 1px solid var(--border); padding: 2px 8px; border-radius: 20px; }
.photo-card-date { font-size: 10px; color: #ccc; margin-top: 5px; }
.btn-delete { font-size: 11px; font-weight: 600; color: #c0392b; background: none; border: 1px solid transparent; cursor: pointer; padding: 3px 8px; border-radius: 5px; font-family: 'Montserrat', sans-serif; }
.btn-delete:hover { background: #fff0f0; border-color: #ffc9c9; }
.btn-delete:disabled { opacity: .5; cursor: default; }
.grid-msg { text-align: center; color: var(--muted); font-size: 13px; padding: 60px 0; grid-column: 1 / -1; }
</style>
</head>
<body>

<!-- Login -->
<div id="login-screen">
  <div class="login-wrap">
    <div class="login-header">
      <h1>Nursify Aesthetics</h1>
      <p>Photo Manager</p>
    </div>
    <div class="card">
      <div id="login-error" class="alert-error" style="display:none"></div>
      <div class="field">
        <label for="secret-input">Password</label>
        <input type="password" id="secret-input" placeholder="Enter upload password" autocomplete="current-password">
      </div>
      <button class="btn-primary" id="login-btn">Sign In</button>
    </div>
  </div>
</div>

<!-- Admin -->
<div id="admin-screen">
  <div class="admin-header">
    <h1>Photo Manager</h1>
    <div class="admin-meta">
      <span id="photo-count"></span>
      <button class="btn-logout" id="logout-btn">Sign out</button>
    </div>
  </div>
  <div class="filter-bar">
    <select id="procedure-filter">
      <option value="">All procedures</option>
      <option value="botox">Botox / Wrinkle Relaxers</option>
      <option value="fillers">Dermal Fillers / Lip Filler</option>
      <option value="microneedling">Microneedling</option>
      <option value="wellness">Wellness Injections</option>
      <option value="weight-loss">Medical Weight Loss</option>
      <option value="prf-hair">PRF Hair Restoration</option>
      <option value="skincare">Skincare</option>
      <option value="reviews">Client Reviews</option>
      <option value="events">Events / Brand</option>
      <option value="general">General / Brand</option>
    </select>
  </div>
  <div class="photo-grid" id="photo-grid">
    <p class="grid-msg">Loading photos&hellip;</p>
  </div>
</div>

<script>
var secret = '';

function qs(id) { return document.getElementById(id); }

function showAdmin() {
  qs('login-screen').style.display = 'none';
  qs('admin-screen').style.display = 'block';
}

function loadPhotos(procedure) {
  var grid = qs('photo-grid');
  grid.innerHTML = '<p class="grid-msg">Loading…</p>';
  var url = '/upload/photos' + (procedure ? '?procedure=' + encodeURIComponent(procedure) : '');
  fetch(url)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var photos = data.photos || [];
      var count = qs('photo-count');
      if (count) count.textContent = photos.length + ' photo' + (photos.length !== 1 ? 's' : '');
      if (!photos.length) {
        grid.innerHTML = '<p class="grid-msg">No photos found.</p>';
        return;
      }
      grid.innerHTML = photos.map(function(p) {
        var date = p.uploaded_at
          ? new Date(p.uploaded_at).toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric'})
          : '';
        return '<div class="photo-card" id="card-' + p.id + '">' +
          '<img src="/upload/thumbnail/' + p.id + '" alt="' + p.title + '" loading="lazy">' +
          '<div class="photo-card-body">' +
            '<div class="photo-card-title" title="' + p.title + '">' + p.title + '</div>' +
            '<div class="photo-card-meta">' +
              '<span class="procedure-badge">' + p.procedure + '</span>' +
              '<button class="btn-delete" data-id="' + p.id + '">Delete</button>' +
            '</div>' +
            (date ? '<div class="photo-card-date">' + date + '</div>' : '') +
          '</div>' +
        '</div>';
      }).join('');

      grid.querySelectorAll('.btn-delete').forEach(function(btn) {
        btn.addEventListener('click', function() {
          if (!confirm('Delete this photo? This cannot be undone.')) return;
          btn.disabled = true;
          btn.textContent = 'Deleting…';
          fetch('/upload/photos/' + btn.dataset.id + '?secret=' + encodeURIComponent(secret), {method: 'DELETE'})
            .then(function(r) { return r.json(); })
            .then(function(res) {
              if (res.success) {
                var card = qs('card-' + btn.dataset.id);
                if (card) { card.style.opacity = '0'; setTimeout(function() { card.remove(); loadPhotos(qs('procedure-filter').value); }, 300); }
              } else {
                btn.disabled = false; btn.textContent = 'Delete';
                alert('Delete failed: ' + (res.detail || 'Unknown error'));
              }
            })
            .catch(function(err) {
              btn.disabled = false; btn.textContent = 'Delete';
              alert('Network error: ' + err.message);
            });
        });
      });
    })
    .catch(function() {
      grid.innerHTML = '<p class="grid-msg">Failed to load photos.</p>';
    });
}

function tryLogin(s) {
  fetch('/upload/photos?limit=1')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.photos !== undefined) {
        secret = s;
        sessionStorage.setItem('nursify_secret', s);
        showAdmin();
        loadPhotos('');
      } else {
        showLoginError('Incorrect password.');
      }
    })
    .catch(function() { showLoginError('Could not connect. Try again.'); });
}

function showLoginError(msg) {
  var el = qs('login-error');
  el.textContent = msg; el.style.display = 'block';
  qs('login-btn').disabled = false;
  qs('login-btn').textContent = 'Sign In';
}

// Auto-login from URL param
(function() {
  var params = new URLSearchParams(window.location.search);
  var s = params.get('s') || sessionStorage.getItem('nursify_secret') || '';
  if (s) {
    qs('secret-input').value = s;
    secret = s;
    showAdmin();
    loadPhotos('');
  }
})();

qs('login-btn').addEventListener('click', function() {
  var s = qs('secret-input').value.trim();
  if (!s) return;
  qs('login-btn').disabled = true;
  qs('login-btn').textContent = 'Signing in…';
  tryLogin(s);
});

qs('secret-input').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') qs('login-btn').click();
});

qs('procedure-filter').addEventListener('change', function() {
  loadPhotos(this.value);
});

qs('logout-btn').addEventListener('click', function() {
  sessionStorage.removeItem('nursify_secret');
  secret = '';
  qs('admin-screen').style.display = 'none';
  qs('login-screen').style.display = 'flex';
  qs('secret-input').value = '';
});
</script>
</body>
</html>"""


# Slug aliases — any of these slugs are returned when the parent slug is queried
PROCEDURE_ALIASES: dict[str, list[str]] = {
    "fillers": ["fillers", "lip-filler"],
    "botox":   ["botox"],
}

# ── GET /photos — used by WordPress photo grid ────────────────────────────────
@upload_router.get("/photos")
async def get_photos(
    procedure:    Optional[str] = None,
    show_on_home: Optional[bool] = None,
    limit:        int = 0,
):
    """
    Returns all photos from Postgres.
    WordPress photo-grid.php calls this to render the grid.
    """
    if not DATABASE_URL:
        return JSONResponse(content={"photos": [], "error": "DATABASE_URL not set"})
    try:
        con = get_db()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        conditions = []
        params     = []

        if procedure:
            slugs = PROCEDURE_ALIASES.get(procedure, [procedure])
            placeholders = ", ".join(["%s"] * len(slugs))
            conditions.append(f"procedure IN ({placeholders})")
            params.extend(slugs)
        if show_on_home is not None:
            conditions.append("show_on_home = %s")
            params.append(show_on_home)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        lim   = f"LIMIT {limit}" if limit > 0 else ""

        cur.execute(f"""
            SELECT id, title, src, instagram_url AS url, procedure,
                   show_on_home, uploaded_at
            FROM nursify_photos
            {where}
            ORDER BY uploaded_at DESC
            {lim}
        """, params)

        rows = cur.fetchall()
        cur.close()
        con.close()

        photos = [dict(r) for r in rows]
        # Convert datetime to string for JSON
        for p in photos:
            if p.get("uploaded_at"):
                p["uploaded_at"] = p["uploaded_at"].isoformat()

        return JSONResponse(content={"photos": photos, "count": len(photos)})

    except Exception as e:
        log.error(f"GET /photos failed: {e}")
        return JSONResponse(content={"photos": [], "error": str(e)}, status_code=500)


# ── POST /result — main upload endpoint ───────────────────────────────────────
@upload_router.post("/result")
async def upload_result(
    photo:         UploadFile    = File(...),
    title:         str           = Form(...),
    instagram_url: str           = Form(...),
    procedure:     str           = Form(...),
    show_on_home:  str           = Form("1"),
    secret:        Optional[str] = Form(None),
    redirect_url:  Optional[str] = Form(None),
):
    # ── 1. Auth ────────────────────────────────────────────────────────
    if secret != UPLOAD_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # ── 2. Validate file ───────────────────────────────────────────────
    if photo.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Use JPG, PNG or WEBP.")

    file_bytes = await photo.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Max 8MB.")

    if not R2_SECRET_ACCESS_KEY:
        raise HTTPException(status_code=503, detail="R2 not configured.")
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="Database not configured.")

    # ── 3. Upload to R2 ────────────────────────────────────────────────
    ext       = photo.filename.rsplit(".", 1)[-1].lower() if "." in photo.filename else "jpg"
    key       = f"results/{uuid.uuid4().hex}.{ext}"
    public_src = f"{R2_PUBLIC_URL}/{key}"

    try:
        r2 = get_r2_client()
        r2.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=file_bytes,
            ContentType=photo.content_type,
        )
        log.info(f"Uploaded to R2: {key}")
    except Exception as e:
        log.error(f"R2 upload failed: {e}")
        raise HTTPException(status_code=502, detail=f"Image storage failed: {str(e)}")

    # ── 4. Save to Postgres ────────────────────────────────────────────
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("""
            INSERT INTO nursify_photos
                (title, src, instagram_url, procedure, show_on_home, source)
            VALUES (%s, %s, %s, %s, %s, 'upload_portal')
            RETURNING id
        """, (
            title,
            public_src,
            instagram_url,
            procedure,
            show_on_home == "1",
        ))
        photo_id = cur.fetchone()[0]
        con.commit()
        cur.close()
        con.close()
        log.info(f"Saved to Postgres: photo ID {photo_id}")
    except Exception as e:
        log.error(f"Postgres insert failed: {e}")
        raise HTTPException(status_code=502, detail=f"Database save failed: {str(e)}")

    # ── 5. Redirect or return JSON ─────────────────────────────────────
    if redirect_url:
        return RedirectResponse(url=redirect_url, status_code=303)

    return JSONResponse(content={
        "success":  True,
        "id":       photo_id,
        "src":      public_src,
        "title":    title,
        "procedure": procedure,
        "message":  "Photo published successfully",
    })


# ── GET /thumbnail/{id} — resized image for the manage grid ──────────────────
@functools.lru_cache(maxsize=500)
def _resize_image(src: str, width: int) -> bytes:
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        r = client.get(src)
        r.raise_for_status()
        raw = r.content
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    orig_w, orig_h = img.size
    if orig_w > width:
        img = img.resize((width, int(orig_h * width / orig_w)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=75, optimize=True)
    return buf.getvalue()


@upload_router.get("/thumbnail/{photo_id}")
def get_thumbnail(photo_id: int):
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT src FROM nursify_photos WHERE id = %s", (photo_id,))
        row = cur.fetchone()
        cur.close(); con.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")
    try:
        data = _resize_image(row[0], 400)
        return Response(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})
    except Exception as e:
        log.error(f"Thumbnail failed for photo {photo_id}: {e}")
        raise HTTPException(status_code=502, detail="Could not process image")


# ── DELETE /photos/{id} ───────────────────────────────────────────────────────
@upload_router.delete("/photos/{photo_id}")
async def delete_photo(photo_id: int, secret: str = Query(...)):
    if secret != UPLOAD_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT src FROM nursify_photos WHERE id = %s", (photo_id,))
        row = cur.fetchone()
        if not row:
            cur.close(); con.close()
            raise HTTPException(status_code=404, detail="Photo not found")
        src = row[0]
        cur.execute("DELETE FROM nursify_photos WHERE id = %s", (photo_id,))
        con.commit()
        cur.close()
        con.close()
        # Remove from R2 if it's an R2-hosted file
        if R2_SECRET_ACCESS_KEY and R2_PUBLIC_URL and src.startswith(R2_PUBLIC_URL):
            try:
                key = src[len(R2_PUBLIC_URL):].lstrip("/")
                get_r2_client().delete_object(Bucket=R2_BUCKET_NAME, Key=key)
            except Exception as e:
                log.warning(f"R2 delete skipped for {src}: {e}")
        return JSONResponse(content={"success": True, "deleted_id": photo_id})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Fix procedure slug ────────────────────────────────────────────────────────
@upload_router.post("/fix-procedure")
async def fix_procedure(
    secret:        str = Form(...),
    old_procedure: str = Form(...),
    new_procedure: str = Form(...),
):
    if secret != UPLOAD_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("UPDATE nursify_photos SET procedure = %s WHERE procedure = %s", (new_procedure, old_procedure))
        updated = cur.rowcount
        con.commit()
        cur.close()
        con.close()
        return JSONResponse(content={"success": True, "updated": updated})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Seed existing hardcoded photos into Postgres ───────────────────────────────
@upload_router.post("/seed")
async def seed_photos(secret: str = Form(...)):
    """
    One-time migration: seeds all existing hardcoded photos into Postgres.
    POST to /upload/seed with secret=nursify-upload-2025
    """
    if secret != UPLOAD_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    hardcoded = [
        {"url": "https://www.instagram.com/p/DU_KamGjeBQ/?img_index=3", "src": "https://nursifyaesthetics.com/wp-content/uploads/2025/12/Service-Menu.jpg",   "alt": "Nursify Aesthetics service menu",                         "cat": "general"},
        {"url": "https://www.instagram.com/p/DVYnfntDfNq/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Expo2026.jpg",         "alt": "Nursify at Expo 2026",                                    "cat": "events"},
        {"url": "https://www.instagram.com/p/DVJNzVwjQ3N/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/MN1.jpg",              "alt": "Microneedling result Albuquerque",                        "cat": "microneedling"},
        {"url": "https://www.instagram.com/p/DVgVPJBkbAC/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/MN2.jpg",              "alt": "SkinPen microneedling result",                           "cat": "microneedling"},
        {"url": "https://www.instagram.com/p/DUa4CIdjeKs/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/CF1.jpg",              "alt": "Chin filler result at Nursify Albuquerque",              "cat": "fillers"},
        {"url": "https://www.instagram.com/p/DWJ_ZMylJU_/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/FacialBalancing1.jpg", "alt": "Facial Balancing Before and After at Nursify Albuquerque","cat": "fillers"},
        {"url": "https://www.instagram.com/p/DVRNv1NjQH2/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Filler8.jpg",          "alt": "Dermal filler result Albuquerque",                       "cat": "fillers"},
        {"url": "https://www.instagram.com/p/DVqi2tfETUi/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Filler7.jpg",          "alt": "Filler result at Nursify",                               "cat": "fillers"},
        {"url": "https://www.instagram.com/p/DU0rHU9jeOk/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Filler6.jpg",          "alt": "Natural-looking filler result",                          "cat": "fillers"},
        {"url": "https://www.instagram.com/p/DUiqCMPFArW/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Filler5.jpg",          "alt": "Juvederm filler result",                                 "cat": "fillers"},
        {"url": "https://www.instagram.com/p/DUVxiRQFH8Y/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Filler4.jpg",          "alt": "Cheek filler enhancement",                              "cat": "fillers"},
        {"url": "https://www.instagram.com/p/DUDv1jKjVBS/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Filler3.jpg",          "alt": "Facial filler before and after",                        "cat": "fillers"},
        {"url": "https://www.instagram.com/p/DTBDE2mkWpc/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/01/Filler2.jpg",          "alt": "Restylane filler result",                               "cat": "fillers"},
        {"url": "https://www.instagram.com/p/DRvgBoujYCN/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2025/12/LipFiller.jpg",        "alt": "Lip filler result Albuquerque",                         "cat": "lip-filler"},
        {"url": "https://www.instagram.com/p/DT-ovB4jVaF/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/LipFlip1.jpg",         "alt": "Lip flip with Botox",                                   "cat": "botox"},
        {"url": "https://www.instagram.com/p/DWEmzfFDRgH/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Botox-Albuquerque15.jpg","alt": "Botox result at Nursify Albuquerque",                  "cat": "botox"},
        {"url": "https://www.instagram.com/p/DV6EWKGlBSH/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Barbie-tox.jpg",       "alt": "Barbie Tox Botox result at Nursify Albuquerque",        "cat": "botox"},
        {"url": "https://www.instagram.com/p/DVbOZVkjW8M/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Botox12.jpg",          "alt": "Botox result Albuquerque",                              "cat": "botox"},
        {"url": "https://www.instagram.com/p/DVOX37ODeS_/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Botox11.jpg",          "alt": "Botox treatment result",                                "cat": "botox"},
        {"url": "https://www.instagram.com/p/DVGtSKBjTev/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Botox10.jpg",          "alt": "Natural Botox result Albuquerque",                      "cat": "botox"},
        {"url": "https://www.instagram.com/p/DU503FNDUJ3/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Botox9.jpg",           "alt": "Crow's feet Botox result",                              "cat": "botox"},
        {"url": "https://www.instagram.com/p/DUlOeR7EUGo/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Botox8.jpg",           "alt": "Frown line Botox treatment",                            "cat": "botox"},
        {"url": "https://www.instagram.com/p/DUTRxpYlCdn/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Botox7.jpg",           "alt": "Botox before and after Nursify",                        "cat": "botox"},
        {"url": "https://www.instagram.com/p/DUGU2MjFIfV/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Botox6.jpg",           "alt": "Wrinkle relaxer results",                               "cat": "botox"},
        {"url": "https://www.instagram.com/p/DTyoibLEgFS/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Botox5.jpg",           "alt": "Botox forehead lines result",                           "cat": "botox"},
        {"url": "https://www.instagram.com/p/DS6I2N7DZW4/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/botox3.jpg",           "alt": "Botox result Albuquerque NM",                           "cat": "botox"},
        {"url": "https://www.instagram.com/p/DSkWcfIjUjW/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/01/botox4.jpg",           "alt": "Xeomin wrinkle relaxer result",                         "cat": "botox"},
        {"url": "https://www.instagram.com/p/DRM2rI_jYpx/?img_index=1",  "src": "https://nursifyaesthetics.com/wp-content/uploads/2025/12/Botox1.jpg",           "alt": "Botox treatment at Nursify Aesthetics",                 "cat": "botox"},
        {"url": "https://www.instagram.com/p/DR42HgzDawz/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2025/12/Wellness-Shot.jpg",     "alt": "Wellness vitamin injection Albuquerque",                "cat": "wellness"},
        {"url": "https://www.instagram.com/p/DSVCL98DQR4/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2025/12/Review1.jpg",           "alt": "Five star review Nursify Aesthetics",                   "cat": "reviews"},
        {"url": "https://www.instagram.com/p/DR7S2IbDdiq/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2025/12/Review2.jpg",           "alt": "Client review Nursify Albuquerque",                     "cat": "reviews"},
        {"url": "https://www.instagram.com/p/DRSI2p2DTL4/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2025/12/Review3.jpg",           "alt": "Happy client review Nursify",                          "cat": "reviews"},
        {"url": "https://www.instagram.com/p/DQ8dlCaDfDQ/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2025/12/Review4.jpg",           "alt": "Client testimonial Nursify Aesthetics",                 "cat": "reviews"},
        {"url": "https://www.instagram.com/p/DTLPe6SFAgY/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Review5.jpg",           "alt": "Five star review Nursify NM",                           "cat": "reviews"},
        {"url": "https://www.instagram.com/p/DUrYl91jSRf/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Review6.jpg",           "alt": "Client review Nursify Aesthetics",                      "cat": "reviews"},
        {"url": "https://www.instagram.com/p/DVMGN2oDbYG/",              "src": "https://nursifyaesthetics.com/wp-content/uploads/2026/03/Review7.jpg",           "alt": "Happy client testimonial Nursify",                      "cat": "reviews"},
    ]

    try:
        con = get_db()
        cur = con.cursor()
        count = 0
        for p in hardcoded:
            cur.execute("""
                INSERT INTO nursify_photos
                    (title, src, instagram_url, procedure, show_on_home, source)
                VALUES (%s, %s, %s, %s, TRUE, 'hardcoded_migration')
                ON CONFLICT DO NOTHING
            """, (p["alt"], p["src"], p["url"], p["cat"]))
            count += 1
        con.commit()
        cur.close()
        con.close()
        return JSONResponse(content={"success": True, "seeded": count})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

import os
import uuid
import logging
import boto3
import psycopg2
import psycopg2.extras

from botocore.config import Config
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
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
            conditions.append("procedure = %s")
            params.append(procedure)
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

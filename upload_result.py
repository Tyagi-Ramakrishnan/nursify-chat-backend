"""
Nursify Photo Upload Endpoint
------------------------------
Handles image uploads from nursifyaesthetics.com/upload
Posts directly to WordPress REST API — no PHP restrictions.

Add to chat.py:
    from upload_result import upload_router
    app.include_router(upload_router)

Railway env vars required:
    WP_URL          = https://nursifyaesthetics.com
    WP_USERNAME     = nursifyaesthetics
    WP_APP_PASSWORD = KK7m RZCD 976j Gnv7 QLt8 Bx6F
    UPLOAD_SECRET   = choose-a-strong-secret (must match page-upload.php)
"""

import os
import base64
import httpx
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional

log = logging.getLogger("nursify.upload")

# ── Config ─────────────────────────────────────────────────────────────────────
WP_URL          = os.environ.get("WP_URL",          "https://nursifyaesthetics.com")
WP_USERNAME     = os.environ.get("WP_USERNAME",     "nursifyaesthetics")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")
UPLOAD_SECRET   = os.environ.get("UPLOAD_SECRET",   "nursify-upload-2025")

ALLOWED_TYPES   = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE   = 8 * 1024 * 1024  # 8MB

upload_router = APIRouter(prefix="/upload", tags=["upload"])


def get_wp_auth() -> str:
    credentials = f"{WP_USERNAME}:{WP_APP_PASSWORD}"
    return "Basic " + base64.b64encode(credentials.encode()).decode()


# ── Health check ───────────────────────────────────────────────────────────────
@upload_router.get("/health")
async def upload_health():
    return {
        "status":      "ok",
        "wp_url":      WP_URL,
        "wp_pass_set": bool(WP_APP_PASSWORD),
        "secret_set":  bool(UPLOAD_SECRET),
    }


# ── Main upload endpoint ───────────────────────────────────────────────────────
@upload_router.post("/result")
async def upload_result(
    photo:         UploadFile    = File(...),
    title:         str           = Form(...),
    instagram_url: str           = Form(...),
    procedure:     str           = Form(...),
    show_on_home:  str           = Form("1"),
    secret:        Optional[str] = Form(None),
):
    # ── 1. Auth ────────────────────────────────────────────────────────
    if secret != UPLOAD_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # ── 2. Validate file ───────────────────────────────────────────────
    if photo.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed: {photo.content_type}. Use JPG, PNG or WEBP."
        )

    file_bytes = await photo.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Max 8MB.")

    if not WP_APP_PASSWORD:
        raise HTTPException(status_code=503, detail="WP_APP_PASSWORD not configured on server.")

    auth_header = get_wp_auth()

    async with httpx.AsyncClient(timeout=30) as client:

        # ── 3. Upload image to WP Media Library ───────────────────────
        log.info(f"Uploading image: {photo.filename}")
        media_resp = await client.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            headers={
                "Authorization":       auth_header,
                "Content-Disposition": f'attachment; filename="{photo.filename}"',
                "Content-Type":        photo.content_type,
            },
            content=file_bytes,
        )

        if media_resp.status_code not in (200, 201):
            log.error(f"Media upload failed: {media_resp.status_code} — {media_resp.text[:300]}")
            raise HTTPException(
                status_code=502,
                detail=f"WP media upload failed ({media_resp.status_code}): {media_resp.text[:200]}"
            )

        attachment_id = media_resp.json().get("id")
        log.info(f"Media uploaded — ID: {attachment_id}")

        # ── 4. Create nursify_result post ──────────────────────────────
        log.info(f"Creating post: {title}")
        post_resp = await client.post(
            f"{WP_URL}/wp-json/wp/v2/nursify_result",
            headers={
                "Authorization": auth_header,
                "Content-Type":  "application/json",
            },
            json={
                "title":          title,
                "status":         "publish",
                "featured_media": attachment_id,
                "meta": {
                    "_nursify_instagram_url":  instagram_url,
                    "_nursify_procedure_type": procedure,
                    "_nursify_show_on_home":   show_on_home,
                },
            },
        )

        if post_resp.status_code not in (200, 201):
            log.error(f"Post creation failed: {post_resp.status_code} — {post_resp.text[:300]}")
            raise HTTPException(
                status_code=502,
                detail=f"WP post creation failed ({post_resp.status_code}): {post_resp.text[:200]}"
            )

        post_id = post_resp.json().get("id")
        log.info(f"Post created — ID: {post_id}")

    return JSONResponse(content={
        "success":       True,
        "post_id":       post_id,
        "attachment_id": attachment_id,
        "message":       "Photo published to nursifyaesthetics.com",
    })

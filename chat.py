"""
Nursify Aesthetics AI Chat Backend
FastAPI + Anthropic Claude Haiku
Deploy on Railway — set ANTHROPIC_API_KEY in environment variables
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List
import anthropic
import os

# After: from intel import intel_router, setup_scheduler, init_db
from upload_result import upload_router



# ── App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Nursify Chat API",
    description="AI chat assistant for Nursify Aesthetics & Wellness",
    version="1.0.0",
)

# ── CORS — open to all origins so the WordPress widget can call it ─────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ── Anthropic client ───────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── System prompt ──────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the virtual assistant for Nursify Aesthetics & Wellness, a luxury nurse-led medical spa in Albuquerque, New Mexico.

BUSINESS INFORMATION:
- Name: Nursify Aesthetics & Wellness
- Address: 5500 San Mateo Blvd NE, Albuquerque, NM 87109
- Phone/Text: (505) 500-7900
- Booking URL: https://nursifyaesthetics.myaestheticrecord.com/online-booking
- Complimentary consultations available
- Owner: Thanisha Daniels, RN BSN — Certified Nurse Injector, 14+ years clinical experience
- Medical Director: Katrina Trujillo, NP
- Concierge in-home services available throughout Albuquerque, Rio Rancho, Santa Fe, and Corrales

HOURS:
- Monday: 9 AM - 5 PM
- Tuesday: 9 AM - 5 PM
- Wednesday: 9 AM - 5 PM
- Thursday: 9 AM - 5 PM
- Friday: 9 AM - 5 PM
- Saturday: 9 AM - 3 PM
- Sunday: Closed

SERVICES AND PRICING:
Botox & Wrinkle Relaxers (Neuromodulators):
We offer three FDA-approved neuromodulators. DAXXIFY is our most popular and recommended option.

- DAXXIFY (most popular): starting at $10/unit + tax. Peptide-powered neuromodulator — the only one that lasts up to 6 months vs 2-3 months for Botox. No human serum albumin. Most clients prefer DAXXIFY for its longevity and fewer appointments per year.
- Botox: starting at $12/unit + tax. Classic FDA-approved neuromodulator, results last 2-3 months.
- Xeomin: also available, priced similarly to Botox.
- All neuromodulator treatment areas: forehead lines, frown lines (11s/glabella), crow's feet, bunny lines, lip flip, chin dimpling (mentalis), masseters (jaw slimming), neck bands (platysma), DAO's (downturned corners of mouth).
- When clients ask about Botox, always mention DAXXIFY as the preferred option and explain the longer-lasting benefit.

Dermal Fillers:
- Juvederm collection: starting at $600/syringe + tax (lips, cheeks, jawline, chin, nasolabial folds, marionette lines)
- Restylane, RHA & Revanesse: starting at $350/syringe + tax (same areas)
- Package discount: 2 syringes save $50, 3 syringes save $100
- Filler dissolving (Hylenex/Hyaluronidase): starting at $300 + tax

SkinPen Microneedling (FDA-cleared):
- Face with Epicutis mask: starting at $325 + tax
- Neck add-on: $75 + tax
- Neck & Décolleté add-on: $150 + tax
- PRP add-on: $150 + tax

PRF Hair Restoration:
- Single session: $500 + tax
- Series of 3 (recommended): $1,350 + tax (save $150)
- Series of 6 (advanced): $2,700 + tax (save $300)

Wellness & Vitamin Injections:
- $35/injection or 4 for $100 + tax (mix and match)
- Available: B12, NAD+, Glutathione, Lipo-Mino-Mix, Biotin, Vitamin D3, Tri-Immune Boost, LipoStat-Plus-SF

Medical Weight Loss:
- Semaglutide: starting at $250/month (medication fully included, monthly consultations included)
- Tirzepatide: starting at $350/month (medication fully included, monthly consultations included)
- Initial consultation with Medical Director required before starting

Epicutis Skincare:
- Pharmaceutical-grade, EWG Verified, fragrance-free skincare line
- Call for pricing: (505) 500-7900

TONE AND RESPONSE GUIDELINES:
- Warm, professional, concise
- Use "we" not "I"
- KEEP RESPONSES SHORT — 2 to 4 sentences maximum. No long paragraphs.
- Lead with the direct answer. Skip preamble like "Great question!" or "Of course!"
- End with one short CTA — either the booking URL or phone number, not both
- Never give medical advice — recommend a consultation instead
- Do not diagnose or recommend specific treatments for health conditions
- New Mexico gross receipts tax applies to all services
- All pricing is starting price — exact pricing confirmed at consultation
- Do NOT use markdown formatting such as **bold**, *italic*, or [text](url). Plain text only.
- Do NOT say you lack information about anything listed in this prompt.
- If someone asks multiple questions, answer the most important one and invite them to ask the rest.

IMPORTANT DISCLAIMERS TO INCLUDE WHEN RELEVANT:
- Treatments are performed by licensed registered nurses with 14+ years experience
- All products are FDA-approved
- Results vary per individual
- A consultation is required before beginning medical weight loss programmes"""

# ── Models ─────────────────────────────────────────────────────────────
class Message(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=2000)

class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., min_length=1, max_length=50)

class ChatResponse(BaseModel):
    reply: str

# ── Mount routers ─────────────────────────────────────────────────────
from intel import intel_router, setup_scheduler, init_db
from upload_result import upload_router

app.include_router(intel_router)
app.include_router(upload_router)

@app.on_event("startup")
async def startup_event():
    init_db()
    from upload_result import init_photos_table
    init_photos_table()
    scheduler = setup_scheduler()
    scheduler.start()

# ── Routes ─────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "Nursify Chat API is running"}

@app.get("/health")
async def health():
    return {"status": "ok", "api_key_set": bool(ANTHROPIC_API_KEY)}

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="API key not configured"
        )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Convert messages to Anthropic format
        anthropic_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            system=SYSTEM_PROMPT,
            messages=anthropic_messages,
        )

        reply = response.content[0].text if response.content else (
            "Thank you for reaching out! Please call or text us at "
            "(505) 500-7900 or book online and we will be happy to help."
        )

        return ChatResponse(reply=reply)

    except anthropic.AuthenticationError:
        raise HTTPException(status_code=503, detail="Authentication error")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="Rate limit reached")
    except Exception as e:
        # Return a graceful message rather than exposing errors
        return ChatResponse(
            reply=(
                "We're experiencing a brief technical issue. Please call or text us "
                "at (505) 500-7900 or book your complimentary consultation online at "
                "https://nursifyaesthetics.myaestheticrecord.com/online-booking — "
                "we'd love to hear from you!"
            )
        )

from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.genai import enforce_lines

from app.settings import settings, SUPPORTED_LANGS
from app import wiki, genai, tts


class LookupRequest(BaseModel):
    lat: float = Field(..., description="Latitude (WGS84)")
    lng: float = Field(..., description="Longitude (WGS84)")
    lang: Optional[str] = Field(None, description="Target language (ISO 639-1)")
    radius: int = Field(8000, ge=100, le=30000, description="Search radius (m)")
    limit: int = Field(8, ge=1, le=20, description="Max candidates")

class Place(BaseModel):
    title: Optional[str]
    normalized_title: Optional[str]
    description: Optional[str]
    extract: Optional[str]
    coordinates: Dict[str, float]
    page_url: Optional[str]
    thumbnail_url: Optional[str]
    original_image_url: Optional[str]
    pageid: Optional[int]
    lang: Optional[str]
    short_summary: Optional[str]
    more_summary: Optional[str]
    ai_blurb: Optional[str] = None  # left for compatibility, always empty here

class LookupResponse(BaseModel):
    best: Optional[Place]
    candidates: List[Place]


class TTSRequest(BaseModel):
    text: str
    lang: Optional[str] = None


app = FastAPI(title="Tourist API (backend only)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/lookup", response_model=LookupResponse)
async def lookup(req: LookupRequest = Body(...)) -> LookupResponse:
    language = (req.lang or settings.DEFAULT_LANG).lower()
    if language not in SUPPORTED_LANGS:
        language = "en"

    raw = await wiki.geosearch_en(req.lat, req.lng, req.radius, req.limit)
    if not raw:
        return LookupResponse(best=None, candidates=[])

    enriched: List[Dict[str, Any]] = []
    for c in raw:
        qid = await wiki.wikidata_qid_for_pageid(c["pageid"])
        target_title = await wiki.title_in_lang_from_qid(qid, language) if qid else None

        used_en_fallback = False
        s = None
        if target_title:
            s = await wiki.summary_in_lang(target_title, language)
        if not s:
            s = await wiki.summary_in_lang(c["title"], "en")
            used_en_fallback = True
        if not s:
            continue

        place = wiki.normalize(c, s, language)

        base_short = " ".join(filter(None, [
            place.get("title"), place.get("description"), place.get("extract")
        ])).strip()

        base_more: Optional[str] = None
        if target_title:
            base_more = await wiki.full_extract(target_title, language)
        if not base_more:
            base_more = await wiki.full_extract(c["title"], "en")

        short_text = await genai.summarize_to_length(
            base_short or (base_more or ""),
            language,
            sentences=5,
            max_chars=700,
        )
        more_text = await genai.summarize_to_length(
            base_more or (place.get("extract") or ""),
            language,
            sentences=15,
            max_chars=3000,
        )

        if used_en_fallback and language != "en":
            place["title"] = await genai.translate_text(place["title"], language) or place["title"]
            if place.get("description"):
                place["description"] = await genai.translate_text(place["description"], language) or place["description"]

        # place["short_summary"] = short_text or (place.get("extract") or "")
        # place["more_summary"] = more_text or place["short_summary"]
        place["short_summary"] = enforce_lines(short_text or (place.get("extract") or ""), 5)
        place["more_summary"]  = enforce_lines(more_text or place["short_summary"], 15)

        enriched.append(place)

    if not enriched:
        return LookupResponse(best=None, candidates=[])

    with_img = [p for p in enriched if p.get("thumbnail_url")]
    best = (with_img or enriched)[0]

    best["ai_blurb"] = None

    best_model = Place(**best)
    cand_models = [Place(**p) for p in enriched]

    return LookupResponse(best=best_model, candidates=cand_models)


@app.post("/api/tts")
async def tts_api(req: TTSRequest = Body(...)):
    language = (req.lang or settings.DEFAULT_LANG).lower()
    if language not in SUPPORTED_LANGS:
        language = "en"
    try:
        audio, mime = await tts.synthesize(req.text.strip(), language, provider="gtts")
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not audio:
        raise HTTPException(status_code=400, detail="gTTS synthesis failed.")
    return StreamingResponse(iter([audio]), media_type=mime)
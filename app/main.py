from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, Query, HTTPException, Body
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.settings import settings, SUPPORTED_LANGS
from app import wiki, genai, tts

app = FastAPI(title="Tourist API")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
def home():
    index = STATIC_DIR / "index.html"
    return FileResponse(str(index))

@app.get("/config")
def get_config():
    return {
        "default_lang": settings.DEFAULT_LANG,
        "tts_provider": settings.TTS_PROVIDER,
        "supported_langs": SUPPORTED_LANGS,
        "gemini_enabled": bool(settings.GEMINI_API_KEY),
    }

@app.get("/api/lookup")
async def lookup(
    lat: float = Query(..., description="Latitude (WGS84)"),
    lng: float = Query(..., description="Longitude (WGS84)"),
    radius: int = Query(8000, ge=100, le=30000),
    limit: int = Query(8, ge=1, le=20),
    lang: Optional[str] = Query(None, description="Target language (ISO 639-1)"),
):
    language = (lang or settings.DEFAULT_LANG).lower()
    if language not in SUPPORTED_LANGS:
        language = "en"

    raw = await wiki.geosearch_en(lat, lng, radius, limit)
    if not raw:
        return {"best": None, "candidates": []}

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

        # Base texts
        base_short = " ".join(filter(None, [
            place.get("title"), place.get("description"), place.get("extract")
        ])).strip()

        base_more: Optional[str] = None
        if target_title:
            base_more = await wiki.full_extract(target_title, language)
        if not base_more:
            base_more = await wiki.full_extract(c["title"], "en")

        # Summaries: short=~5 lines, long=~15 lines (Gemini if available; safe fallback otherwise)
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

        # Translate title/description if we fell back to EN
        if used_en_fallback and language != "en":
            place["title"] = await genai.translate_text(place["title"], language) or place["title"]
            if place.get("description"):
                place["description"] = await genai.translate_text(place["description"], language) or place["description"]

        place["short_summary"] = short_text or (place.get("extract") or "")
        place["more_summary"]  = more_text or place["short_summary"]

        enriched.append(place)

    if not enriched:
        return {"best": None, "candidates": []}

    with_img = [p for p in enriched if p.get("thumbnail_url")]
    best = (with_img or enriched)[0]

    best["ai_blurb"] = await genai.make_blurb(
        best["title"], best.get("description") or "",
        best.get("short_summary") or "",
        best.get("page_url") or "", language
    )

    return {"best": best, "candidates": enriched}

@app.post("/api/tts")
async def tts_gtts(text: str = Body(..., embed=True), lang: Optional[str] = Body(None)):
    language = (lang or settings.DEFAULT_LANG).lower()
    if language not in SUPPORTED_LANGS:
        language = "en"
    try:
        audio, mime = await tts.synthesize(text.strip(), language, provider="gtts")
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not audio:
        raise HTTPException(status_code=400, detail="gTTS synthesis failed.")
    return StreamingResponse(iter([audio]), media_type=mime)
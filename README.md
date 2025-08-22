# 🌍 Tourist Info API

A FastAPI backend that lets you query Wikipedia for tourist places by latitude/longitude and get:
- 📍 Stable tourist places near coordinates (via **English Wikipedia only** to avoid changing results when switching languages).
- 📖 Summaries in multiple languages:
  - Short summary (~5 lines)
  - Long summary (~15 lines)
- 🔊 Server-side TTS (MP3 via gTTS)

This project is designed for use with mobile apps or web frontends. All logic is in Python, so the frontend can be swapped or removed easily. Made with only opensource links and free models.

---

## 🚨 Important Note on Language & Location
Initially, when the app switched languages, **the places returned also changed** (because geosearch was happening in that language’s Wikipedia).  

👉 To fix this, the system now always performs **geosearch on English Wikipedia only**, then:
- Resolves the **Wikidata QID** for each place.
- Maps it to the user’s selected language (if available).
- Falls back to English and translates text if no local-language page exists.

✅ Result: The **locations remain stable**, while summaries/descriptions change to the user’s chosen language.

---

## 📦 Installation

Clone and install dependencies:

```bash
git clone https://github.com/your-username/tourist_app.git
cd tourist_app
pip install -r requirements.txt
```

## ▶️ Run the server
```bash
uvicorn app.main:app --reload
```
- API root: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs

## 🔗 Endpoints
1. Lookup Tourist Info
```
POST /api/lookup
```
Request body
```json
{
  "lat": 48.8584,
  "lng": 2.2945,
  "lang": "en",
  "radius": 8000,
  "limit": 5
}
```

Response (sample)
```json
{
  "best": {
    "title": "Eiffel Tower",
    "description": "Tower in Paris, France",
    "page_url": "https://en.wikipedia.org/wiki/Eiffel_Tower",
    "thumbnail_url": "https://upload.wikimedia.org/...jpg",
    "short_summary": "Short summary in ~5 lines...",
    "more_summary": "Longer summary in ~15 lines..."
  },
  "candidates": [...]
}
```

2. Text-to-Speech
```
POST /api/tts
```

Request body
```json
{ "text": "Hello from Paris", "lang": "en" }
```
Response
- Returns MP3 audio of the text.

## ⚙️ Config

- DEFAULT_LANG → default language code (en, fr, etc.)
- Short summary → 5 lines
- Long summary → 15 lines
- Logic in: app/main.py, app/wiki.py, app/tts.py, app/settings.py

## 📂 Project Structure

```bash
tourist_app/
├── app/
│   ├── main.py        # FastAPI app, endpoints
│   ├── wiki.py        # Wikipedia + Wikidata fetch
│   ├── genai.py       # (Optional) Gemini integration
│   ├── tts.py         # gTTS synthesis
│   ├── settings.py    # Configurations
├── requirements.txt
└── README.md
```

## 🧪 Testing
### Lookup (PowerShell)
```powershell
$body = @{ lat = 48.8584; lng = 2.2945; lang = "en"; radius = 8000; limit = 5 } | ConvertTo-Json
$resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/lookup" -Method POST -ContentType "application/json" -Body $body
$data = $resp.Content | ConvertFrom-Json
$data.best.short_summary
$data.best.more_summary
```

### TTS
```powershell
$ttsBody = '{"text":"Hello from Paris","lang":"en"}'
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/tts" -Method POST -ContentType "application/json" -Body $ttsBody -OutFile "tts_en.mp3"
Start-Process "tts_en.mp3"
```

import os
import re
import io
import json
import sqlite3
import hashlib
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv()

GNANI_API_KEY = os.getenv("GNANI_API_KEY", "")
PRISMA_ENDPOINT = "https://api.vachana.ai/stt/v3"
TIMBRE_ENDPOINT = "https://api.vachana.ai/api/v1/tts/inference"
CACHE_DIR = Path("backend/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="BolKhata Voice Finance Engine", version="1.0.0")

# Critical: Strict concurrency lock to avoid 429 RATE_LIMITED on developer tier
GNANI_API_LOCK = asyncio.Lock()

# ----------------- Database Setup -----------------
DB_PATH = "backend/bolkhata.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            raw_text TEXT,
            amount REAL,
            category TEXT,
            merchant TEXT,
            tx_type TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ----------------- Deterministic Multilingual NLP Parser -----------------
CATEGORY_KEYWORDS = {
    "Food": [
        "swiggy", "zomato", "biryani", "khana", "lunch", "dinner", "chai", "tiffin", "restaurant", "hotel", "samosa",
        "चाय", "खाना", "बिरयानी", "समोसा", "होटल",
        "బిర్యానీ", "బిర్యానీకి", "చాయ్", "టిఫిన్", "భోజనం"
    ],
    "Groceries": [
        "sabzi", "kirana", "dukan", "milk", "vegetables", "doodh", "ration", "store", "supermarket", "groceries",
        "सब्जी", "किराना", "दुकान", "दूध", "राशन",
        "కిరాణా", "కూరగాయలు", "పాలు", "దుకాణం"
    ],
    "Transit": [
        "uber", "ola", "auto", "petrol", "diesel", "metro", "bus", "rapido", "cab",
        "ऑटो", "पेट्रोल", "बस", "मेट्रो", "कैब",
        "ఆటో", "పెట్రోల్", "బస్సు", "మెట్రో"
    ],
    "Shopping": [
        "amazon", "flipkart", "clothes", "kapde", "mall", "shopping",
        "कपड़े", "शॉपिंग", "బట్టలు", "షాపింగ్"
    ],
    "Utilities": [
        "bill", "current", "recharge", "wifi", "rent", "water", "electricity",
        "बिल", "रिचार्ज", "किराया", "బిల్లు", "రీఛార్జ్", "కరెంట్", "అద్దె"
    ]
}

# Maps English, Hindi (Devanagari & Roman), and Telugu number words to values
WORD_NUMBERS = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
    # Hindi (Devanagari)
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15, "सोलह": 16, "सत्रह": 17, "अठारह": 18,
    "उन्नीस": 19, "बीस": 20, "पच्चीस": 25, "तीस": 30, "पैंतीस": 35, "चालीस": 40, "पैंतालीस": 45, "पचास": 50,
    "साठ": 60, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90, "डेढ़": 1.5, "ढाई": 2.5,
    # Hindi (Romanized)
    "ek": 1, "do": 2, "teen": 3, "chaar": 4, "char": 4, "paanch": 5, "panch": 5, "saat": 7, "aath": 8, "nau": 9,
    "das": 10, "bees": 20, "pachis": 25, "tees": 30, "chalis": 40, "pachas": 50, "saath": 60, "sattar": 70, "assi": 80, "nabbe": 90,
    # Telugu (Script & Romanized)
    "ఒక": 1, "ఒకటి": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4, "ఐదు": 5, "ఆరు": 6, "ఏడు": 7, "ఎనిమిది": 8, "తొమ్మిది": 9,
    "పది": 10, "ఇరవై": 20, "ముప్పై": 30, "నలభై": 40, "యాభై": 50, "అరవై": 60, "డెబ్బై": 70, "ఎనభై": 80, "తొంభై": 90,
    "iravai": 20, "muppai": 30, "nalabhai": 40, "yabhai": 50, "aravai": 60, "debbai": 70, "enabhai": 80, "tombhai": 90
}

MULTIPLIERS = {
    "hundred": 100, "सौ": 100, "sau": 100, "వంద": 100, "వందల": 100, "నూట": 100, "vanda": 100, "noota": 100,
    "thousand": 1000, "हज़ार": 1000, "हजार": 1000, "hazaar": 1000, "hazar": 1000, "వెయ్యి": 1000, "వేల": 1000, "veyyi": 1000
}

def parse_spoken_amount(text: str) -> float:
    # 1. Check for standard numeric digits first (e.g., "350", "120")
    digit_match = re.search(r'(?:₹|rs\.?|inr|rupees?)?\s*(\d+(?:\.\d{1,2})?)', text)
    if digit_match:
        return float(digit_match.group(1))

    # 2. Parse spoken number words across English, Hindi, and Telugu
    clean_text = re.sub(r'[.,।!?]', ' ', text.lower())
    tokens = clean_text.split()

    total = 0.0
    current = 0.0
    last_unit = 0.0

    for token in tokens:
        if token in WORD_NUMBERS:
            val = WORD_NUMBERS[token]
            # Handle spoken shorthand like "three fifty" (350) or "one twenty" (120)
            if 1 <= last_unit <= 9 and 10 <= val <= 99 and current == last_unit:
                current = (last_unit * 100) + val
            else:
                current += val
            last_unit = val
        elif token in MULTIPLIERS:
            mult = MULTIPLIERS[token]
            current = (current if current > 0 else 1.0) * mult
            if mult >= 1000:
                total += current
                current = 0.0
            last_unit = 0.0

    return total + current

def extract_transaction_details(text: str) -> Dict[str, Any]:
    text_lower = text.lower()
    
    # 1. Extract Amount (Digits or Multilingual Words)
    amount = parse_spoken_amount(text_lower)
            
    # 2. Transaction Type (Spent vs Received)
    tx_type = "Debit"
    credit_keywords = ["aaye", "mila", "credited", "received", "vachayi", "iccharu", "आये", "मिला", "వచ్చాయి", "ఇచ్చారు"]
    if any(k in text_lower for k in credit_keywords):
        tx_type = "Credit"

    # 3. Category Detection (Matches English, Hindi, and Telugu scripts)
    category = "General"
    detected_merchant = "Direct"
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                category = cat
                detected_merchant = kw.capitalize()
                break
        if category != "General":
            break

    return {
        "amount": amount,
        "category": category,
        "merchant": detected_merchant,
        "tx_type": tx_type
    }


# ----------------- Endpoints -----------------

@app.post("/api/record-voice")
async def record_voice(
    audio: UploadFile = File(...),
    preferred_language: str = Form("indic-auto")
):
    if not GNANI_API_KEY:
        raise HTTPException(status_code=500, detail="GNANI_API_KEY not configured.")

    audio_bytes = await audio.read()
    
    # 1. Transcribe with Prisma v3.0
    headers = {"X-API-Key-ID": GNANI_API_KEY}
    files = {"audio_file": (audio.filename or "audio.wav", audio_bytes, audio.content_type or "audio/wav")}
    # Inside @app.post("/api/record-voice") — replace the payload dictionary:
    payload = {
        "model": "prisma-v3.0",
        "language_code": preferred_language,
        "format": "codemix",
        "topic": "Indian personal finance, UPI merchant payments, daily household expenses, food delivery, and transit fares in Hinglish and Telugu.",
        "keyterms": json.dumps(["Swiggy", "Zomato", "Rapido", "Kirana", "UPI", "Petrol", "Biryani", "Auto"]),
        "substitution_map": json.dumps({"three fifty": "350", "one twenty": "120", "rupees": "₹", "rupaye": "₹"})
    }
    async with GNANI_API_LOCK:
        try:
            resp = requests.post(PRISMA_ENDPOINT, headers=headers, files=files, data=payload, timeout=30)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            stt_data = resp.json()
            transcript = stt_data.get("transcript", "").strip()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Prisma ASR Error: {str(e)}")

    if not transcript:
        return {"success": False, "message": "No audible speech recognized."}

    # 2. Parse text
    parsed = extract_transaction_details(transcript)
    
    # 3. Store in DB
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions (timestamp, raw_text, amount, category, merchant, tx_type) VALUES (?, ?, ?, ?, ?, ?)",
        (now_str, transcript, parsed["amount"], parsed["category"], parsed["merchant"], parsed["tx_type"])
    )
    conn.commit()
    conn.close()

    # 4. Generate Spoken Feedback Message (Timbre TTS)
    feedback_text = (
        f"Noted. {parsed['tx_type']} of {int(parsed['amount'])} rupees for {parsed['category']}."
    )
    
    # MD5 caching to preserve Timbre character quota
    tts_hash = hashlib.md5((feedback_text + "_Nalini").encode("utf-8")).hexdigest()
    tts_file_path = CACHE_DIR / f"{tts_hash}.wav"

    if not tts_file_path.exists():
        tts_payload = {
            "text": feedback_text,
            "voice": "Nalini",
            "model": "timbre-v2.5",
            "language": "hi-IN",
            "audio_config": {
                "sample_rate": 24000,
                "encoding": "linear_pcm",
                "container": "wav"
            }
        }
        async with GNANI_API_LOCK:
            try:
                tts_resp = requests.post(
                    TIMBRE_ENDPOINT,
                    headers={"Content-Type": "application/json", "X-API-Key-ID": GNANI_API_KEY},
                    json=tts_payload,
                    timeout=30
                )
                if tts_resp.status_code == 200:
                    with open(tts_file_path, "wb") as f:
                        f.write(tts_resp.content)
            except Exception:
                pass  # Fall back gracefully without failing the transaction

    return {
        "success": True,
        "transcript": transcript,
        "parsed": parsed,
        "feedback_text": feedback_text,
        "tts_cached_id": tts_hash if tts_file_path.exists() else None
    }

@app.get("/api/audio/{audio_id}")
def get_audio(audio_id: str):
    file_path = CACHE_DIR / f"{audio_id}.wav"
    if file_path.exists():
        return FileResponse(file_path, media_type="audio/wav")
    raise HTTPException(status_code=404, detail="Audio file not found")

@app.get("/api/transactions")
def get_transactions():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/api/seed-demo")
def seed_demo_data():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions WHERE amount = 0")
    synthetic_rows = [
        ("2026-11-05 09:15:00", "Metro card recharge ke liye 500 rupaye diye", 500.0, "Transit", "Metro", "Debit"),
        ("2026-11-05 14:30:00", "Zomato lo lunch kosam 280 pay chesaanu", 280.0, "Food", "Zomato", "Debit"),
        ("2026-11-06 11:00:00", "Kirana dukan pe doodh aur sabzi ke 450 diye", 450.0, "Groceries", "Kirana", "Debit"),
        ("2026-11-06 19:45:00", "Wifi bill recharge 799 rupees completed", 799.0, "Utilities", "Wifi", "Debit"),
        ("2026-11-07 10:00:00", "Friend nundi 1500 rupaye UPI lo vachayi", 1500.0, "General", "Direct", "Credit"),
    ]
    cur.executemany(
        "INSERT INTO transactions (timestamp, raw_text, amount, category, merchant, tx_type) VALUES (?, ?, ?, ?, ?, ?)",
        synthetic_rows
    )
    conn.commit()
    conn.close()
    return {"status": "seeded"}

@app.delete("/api/reset")
def reset_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions")
    conn.commit()
    conn.close()
    return {"status": "cleared"}
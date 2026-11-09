# 🎙️ BolKhata: Voice-First Indic & Code-Mixed Expense Ledger

Built for the **Gnani.ai Great Indian AI Internship Challenge 2026** (`#GreatIndianAIInternshipChallenge` `#GnaniAI`).

## 1. Problem & Target Users
Millions of Indian consumers, students, and small kirana merchants track daily expenses colloquially across code-mixed languages (Telugu-English, Hinglish) rather than typing into complex spreadsheet apps. **BolKhata** turns natural, unstructured 5-second voice notes into structured financial ledger entries with real-time spoken confirmation.

## 2. Gnani.ai Technology & Models Used
* **Speech-to-Text (ASR): Gnani Prisma v3.0 (`https://api.vachana.ai/stt/v3`)**
  * Configured with `language_code="indic-auto"` and `format="codemix"` to transcribe Telugu, Hindi, and English code-mixed utterances.
  * Uses contextual `topic` steering, `keyterms` biasing (`Swiggy`, `Zomato`, `Kirana`, `UPI`), and `substitution_map` normalization.
* **Text-to-Speech (TTS): Gnani Timbre v2.5 (`https://api.vachana.ai/api/v1/tts/inference`)**
  * Synthesizes instant audio confirmation using the `Nalini` voice persona at `24000 Hz` (`linear_pcm` / `wav`).

## 3. System Engineering & Resource Optimization
* **Single-Request Concurrency Lock:** Enforces an `asyncio.Lock()` queue around upstream calls to respect the developer tier's 1-active-request concurrency limit and prevent `HTTP 429 RATE_LIMITED` errors.
* **MD5 TTS Audio Caching:** Hashes outgoing confirmation strings (`MD5(text + voice)`) and caches `.wav` responses locally to conserve the 5,000 developer credit quota.
* **Multilingual Deterministic NLP Parser:** Extracts numerical digits alongside spoken Hindi, Telugu, and English number words across native Indic scripts and Latin transliterations.
* **100% DPDP Act Compliant:** Uses strictly synthetic financial transactions and consensual test audio with zero real banking PII.

## 4. Current Limitations & What I Would Fix Next
* **Noisy Telephony Downsampling:** Currently optimized for browser microphone WAV inputs; next iteration will add WebSocket streaming (`wss://`) with explicit `x-vad-threshold` tuning (`0.72`) for noisy outdoor street markets.
* **Complex Multi-Item Splits:** If a user speaks 3 different expenses in a single breath, the deterministic parser logs the primary category. Integrating Gnani's **Evon v3.3** model next will allow multi-intent JSON extraction from a single voice note.

## 5. How to Run Locally

1. **Clone the repository and install dependencies:**
   ```bash
   git clone [https://github.com/B-PranayKumar/bolkhata-gnani-ai.git](https://github.com/B-PranayKumar/bolkhata-gnani-ai.git)
   cd bolkhata-gnani-ai
   python -m venv venv
   ```
   Activate the virtual environment and install packages:
   * **Windows:** `.\venv\Scripts\activate`
   * **Mac/Linux:** `source venv/bin/activate`
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables:**
   Create a `.env` file in the root directory and add your Gnani.ai API key:
   ```env
   GNANI_API_KEY=your_gnani_api_key_here
   FASTAPI_HOST=http://localhost:8000
   ```

3. **Start the FastAPI backend (Terminal 1):**
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

4. **Start the Streamlit frontend (Terminal 2):**
   ```bash
   streamlit run frontend/app.py
   ```

5. **Open the dashboard:**
   Visit `http://localhost:8501` in your browser, click **✨ Seed Synthetic Data (Clean ₹0)** in the sidebar, and click the microphone icon to record a voice transaction in Telugu-English or Hinglish.

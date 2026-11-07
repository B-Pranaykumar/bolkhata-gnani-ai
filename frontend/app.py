import os
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from audio_recorder_streamlit import audio_recorder
from dotenv import load_dotenv

load_dotenv()
API_BASE = os.getenv("FASTAPI_HOST", "http://localhost:8000")

st.set_page_config(
    page_title="BolKhata | Indic Voice Expense Ledger",
    page_icon="🎙️",
    layout="wide"
)

# ----------------- Styles & Header -----------------
st.markdown("""
    <style>
    .metric-card { background-color: #f8f9fa; border-radius: 8px; padding: 15px; border-left: 5px solid #28a745; }
    </style>
""", unsafe_allow_html=True)

st.title("🎙️ BolKhata: Voice-First Indic Expense Tracker")
st.caption("Powered by Gnani Prisma v3.0 (ASR) & Timbre v2.5 (TTS) • 100% Synthetic DPDP Compliant")

# ----------------- Sidebar Control -----------------
with st.sidebar:
    st.header("Engine Settings")
    lang_choice = st.selectbox(
        "Prisma ASR Language Model",
        options=["indic-auto", "hi-IN", "te-IN", "ta-IN", "kn-IN", "en-IN"],
        index=0,
        help="Select 'indic-auto' for automated dialect and code-mixed recognition."
    )
    st.info("💡 **Voice Tip:** Speak naturally in Hinglish or Telugu:\n\n* 'Swiggy lo biryani ki 350 pay chesaanu'\n* 'Chai aur samosa ke liye assi rupaye diye'\n* 'Auto wale ko 120 rupaye transfer kiya'")
    st.divider()
    st.subheader("Demo Controls")
    if st.button("✨ Seed Synthetic Data (Clean ₹0)"):
        requests.post(f"{API_BASE}/api/seed-demo")
        st.rerun()
    if st.button("🗑️ Reset All Transactions"):
        requests.delete(f"{API_BASE}/api/reset")
        st.rerun()

# ----------------- Top Section: Voice Input -----------------
st.subheader("1. Speak Transaction")
col_rec, col_stat = st.columns([1, 2])

with col_rec:
    st.write("Click mic to record (auto-stops on silence):")
    audio_bytes = audio_recorder(
        text="",
        recording_color="#e74c3c",
        neutral_color="#2c3e50",
        icon_size="2x",
        pause_threshold=2.0
    )

if audio_bytes:
    with col_stat:
        with st.spinner("Processing speech via Gnani Prisma v3.0..."):
            files = {"audio": ("input.wav", audio_bytes, "audio/wav")}
            data = {"preferred_language": lang_choice}
            try:
                res = requests.post(f"{API_BASE}/api/record-voice", files=files, data=data)
                if res.status_code == 200:
                    payload = res.json()
                    if payload.get("success"):
                        st.success(f"**Transcribed:** \"{payload['transcript']}\"")
                        p = payload["parsed"]
                        st.markdown(f"**Parsed:** ₹{p['amount']} | Category: `{p['category']}` | Type: `{p['tx_type']}`")
                        
                        # Audio playback of Timbre voice
                        if payload.get("tts_cached_id"):
                            st.audio(f"{API_BASE}/api/audio/{payload['tts_cached_id']}", format="audio/wav")
                        with st.expander("🔍 View Gnani Prisma v3.0 & Timbre v2.5 Telemetry", expanded=True):
                            st.json({
                                "asr_engine": "Gnani Prisma v3.0 (api.vachana.ai/stt/v3)",
                                "language_mode": lang_choice,
                                "raw_transcript": payload["transcript"],
                                "extracted_entity": payload["parsed"],
                                "tts_engine": "Gnani Timbre v2.5 (Voice: Nalini)",
                                "tts_cache_key": payload.get("tts_cached_id")
                            })
                    else:
                        st.warning(payload.get("message", "Could not recognize audio."))
                else:
                    st.error(f"Error {res.status_code}: {res.text}")
            except Exception as e:
                st.error(f"Failed to connect to backend: {e}")

st.divider()

# ----------------- Bottom Section: Analytics & Ledger -----------------
st.subheader("2. Ledger & Spending Analytics")

try:
    tx_res = requests.get(f"{API_BASE}/api/transactions")
    tx_data = tx_res.json() if tx_res.status_code == 200 else []
except Exception:
    tx_data = []

if tx_data:
    df = pd.DataFrame(tx_data)
    df["amount"] = pd.to_numeric(df["amount"])
    
    # High-level Metrics
    total_spent = df[df["tx_type"] == "Debit"]["amount"].sum()
    total_received = df[df["tx_type"] == "Credit"]["amount"].sum()
    tx_count = len(df)
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Debits", f"₹{total_spent:,.2f}")
    m2.metric("Total Credits", f"₹{total_received:,.2f}")
    m3.metric("Logged Entries", tx_count)

    st.write("")
    col_chart, col_table = st.columns([1, 1])

    with col_chart:
        # Category Pie Breakdown
        debit_df = df[df["tx_type"] == "Debit"]
        if not debit_df.empty:
            cat_sum = debit_df.groupby("category")["amount"].sum().reset_index()
            fig = px.pie(
                cat_sum,
                values="amount",
                names="category",
                hole=0.4,
                title="Expenses by Category",
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            fig.update_layout(margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No debit transactions recorded yet.")

    with col_table:
        st.write("**Recent Entries**")
        st.dataframe(
            df[["timestamp", "category", "amount", "tx_type", "raw_text"]].head(8),
            use_container_width=True,
            hide_index=True
        )
else:
    st.info("No voice transactions logged yet. Record your first expense above!")
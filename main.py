import os
import time

import requests
import streamlit as st
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException
from google import generativeai as genai
from google.api_core import retry, exceptions as google_exceptions

from api import extract_prescription_from_bytes


st.set_page_config(
    page_title="CliniGuide AI",
    page_icon="medical_symbol",
    layout="wide",
)

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    GOOGLE_API_KEY = GOOGLE_API_KEY.strip().strip('"').strip("'")
if not GOOGLE_API_KEY:
    st.error(
        "Missing GOOGLE_API_KEY. Create a `.env` file next to `main.py` with:\n\n"
        "GOOGLE_API_KEY=your_key_here"
    )
    st.stop()

genai.configure(api_key=GOOGLE_API_KEY)


def inject_styles(theme_mode: str):
    if theme_mode == "Dark":
        palette = """
        :root {
            --bg: #0d1517;
            --surface: rgba(18, 31, 35, 0.90);
            --surface-strong: #142227;
            --surface-elevated: rgba(24, 39, 44, 0.98);
            --ink: #eff7f4;
            --muted: #b9cac4;
            --line: rgba(210, 229, 223, 0.12);
            --accent: #58d3b4;
            --accent-2: #f5a36c;
            --shadow: 0 22px 44px rgba(0, 0, 0, 0.34);
            --input-bg: rgba(9, 18, 21, 0.92);
            --input-ink: #f4fbf8;
            --table-head: rgba(88, 211, 180, 0.14);
            --success-bg: rgba(36, 88, 75, 0.38);
            --warn-bg: rgba(106, 79, 33, 0.34);
            --info-bg: rgba(27, 70, 86, 0.34);
        }
        """
        app_background = """
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(88, 211, 180, 0.18), transparent 24%),
                radial-gradient(circle at top right, rgba(245, 163, 108, 0.16), transparent 22%),
                linear-gradient(180deg, #0f181b 0%, var(--bg) 44%, #091113 100%);
            color: var(--ink);
        }
        """
        hero_background = "background: linear-gradient(140deg, rgba(18,31,35,0.98), rgba(22,37,42,0.92)); border: 1px solid rgba(210, 229, 223, 0.08);"
        sidebar_background = "background: linear-gradient(180deg, #081315 0%, #0b191c 100%); border-right: 1px solid rgba(255,255,255,0.07);"
    else:
        palette = """
        :root {
            --bg: #f4efe6;
            --surface: rgba(255, 251, 245, 0.88);
            --surface-strong: #fffaf2;
            --surface-elevated: rgba(255, 252, 247, 0.98);
            --ink: #1f2f2a;
            --muted: #5d6f68;
            --line: rgba(31, 47, 42, 0.12);
            --accent: #0e7c66;
            --accent-2: #c96d42;
            --shadow: 0 18px 44px rgba(53, 67, 61, 0.10);
            --input-bg: rgba(255, 255, 255, 0.88);
            --input-ink: #17312a;
            --table-head: rgba(14, 124, 102, 0.08);
            --success-bg: rgba(166, 223, 205, 0.35);
            --warn-bg: rgba(244, 203, 159, 0.35);
            --info-bg: rgba(177, 219, 235, 0.35);
        }
        """
        app_background = """
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(14, 124, 102, 0.15), transparent 24%),
                radial-gradient(circle at top right, rgba(201, 109, 66, 0.14), transparent 20%),
                linear-gradient(180deg, #f8f4ed 0%, var(--bg) 48%, #efe7da 100%);
            color: var(--ink);
        }
        """
        hero_background = "background: linear-gradient(140deg, rgba(255,250,242,0.96), rgba(248,239,228,0.9)); border: 1px solid rgba(31, 47, 42, 0.08);"
        sidebar_background = "background: linear-gradient(180deg, #17342e 0%, #102722 100%); border-right: 1px solid rgba(255,255,255,0.08);"

    style_template = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Source+Serif+4:wght@400;600&display=swap');

        __PALETTE__

        __APP_BACKGROUND__

        .stApp, .stMarkdown, .stText, .stAlert, .stCaption, label, p, li, div, span {
            font-family: "Space Grotesk", sans-serif;
        }

        h1, h2, h3, h4, h5, h6 {
            color: var(--ink);
            letter-spacing: -0.03em;
        }

        p, li, label, .stMarkdown, .stText, .stCaption, small, strong, em {
            color: var(--ink);
        }

        a {
            color: var(--accent);
        }

        hr {
            border-color: var(--line);
        }

        .block-container {
            padding-top: 2.2rem;
            padding-bottom: 2rem;
            max-width: 1180px;
        }

        .main .block-container {
            width: min(1180px, 100%);
        }

        .hero-shell {
            __HERO_BACKGROUND__
            border-radius: 28px;
            padding: 2rem 2rem 1.7rem 2rem;
            box-shadow: var(--shadow);
            position: relative;
            overflow: hidden;
            margin-bottom: 1.2rem;
        }

        .hero-shell::after {
            content: "";
            position: absolute;
            inset: auto -80px -100px auto;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(14,124,102,0.18), transparent 70%);
        }

        .eyebrow {
            display: inline-block;
            background: rgba(14, 124, 102, 0.11);
            color: var(--accent);
            border-radius: 999px;
            padding: 0.35rem 0.7rem;
            font-size: 0.82rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }

        .hero-title {
            font-family: "Source Serif 4", serif;
            font-size: clamp(2.4rem, 4vw, 4rem);
            line-height: 0.96;
            margin: 0.75rem 0 0.85rem 0;
        }

        .hero-copy {
            max-width: 760px;
            color: var(--muted);
            font-size: 1.02rem;
            line-height: 1.6;
        }

        .metric-row {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.9rem;
            margin-top: 1.4rem;
        }

        .metric-card, .section-card {
            background: linear-gradient(180deg, var(--surface), var(--surface-elevated));
            border: 1px solid var(--line);
            border-radius: 22px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(6px);
        }

        .metric-card {
            padding: 1rem 1.1rem;
        }

        .metric-card strong {
            display: block;
            font-size: 1.35rem;
            color: var(--ink);
            margin-bottom: 0.2rem;
        }

        .metric-card span {
            color: var(--muted);
            font-size: 0.92rem;
        }

        .section-card {
            padding: 1.2rem 1.2rem 1rem 1.2rem;
            margin-bottom: 1rem;
            min-height: 100%;
        }

        .section-title {
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
            color: var(--ink);
        }

        .section-subtitle {
            color: var(--muted);
            font-size: 0.92rem;
            margin-bottom: 0.8rem;
        }

        [data-testid="stSidebar"] {
            __SIDEBAR_BACKGROUND__
        }

        [data-testid="stSidebar"] * {
            color: #f7f2ea;
        }

        [data-testid="stSidebar"] .stSelectbox label,
        [data-testid="stSidebar"] .stCheckbox label,
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] p {
            color: #f7f2ea !important;
        }

        [data-testid="stFileUploader"] section,
        .stTextInput > div > div,
        .stTextArea textarea,
        .stSelectbox > div > div,
        .stMultiSelect > div > div,
        .stTextInput input {
            background: var(--input-bg) !important;
            border-radius: 16px;
            color: var(--input-ink) !important;
            border: 1px solid var(--line) !important;
        }

        .stTextArea textarea::placeholder,
        .stTextInput input::placeholder {
            color: var(--muted) !important;
        }

        .stTextArea textarea,
        .stTextInput input,
        [data-baseweb="select"] *,
        [data-baseweb="tag"] {
            color: var(--input-ink) !important;
        }

        .stSelectbox label,
        .stTextInput label,
        .stTextArea label,
        .stFileUploader label,
        .stCheckbox label {
            color: var(--ink) !important;
        }

        [data-testid="stFileUploader"] small,
        [data-testid="stFileUploader"] span,
        [data-testid="stFileUploader"] div {
            color: var(--ink) !important;
        }

        .stButton > button {
            width: 100%;
            border: none;
            border-radius: 16px;
            background: linear-gradient(135deg, var(--accent), #075948);
            color: #f9f5ee;
            padding: 0.8rem 1rem;
            font-weight: 700;
            box-shadow: 0 12px 24px rgba(14, 124, 102, 0.25);
        }

        .stButton > button:hover {
            background: linear-gradient(135deg, #0c6b59, #06483b);
        }

        .result-card {
            background: var(--surface-strong);
            border: 1px solid var(--line);
            border-radius: 22px;
            padding: 1.2rem;
            box-shadow: var(--shadow);
            margin-bottom: 1rem;
            overflow: hidden;
        }

        .result-title {
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 0.7rem;
            color: var(--ink);
        }

        .panel-kicker {
            display: inline-block;
            margin-bottom: 0.55rem;
            padding: 0.28rem 0.62rem;
            border-radius: 999px;
            background: var(--table-head);
            color: var(--accent);
            font-size: 0.78rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .section-stack {
            display: grid;
            gap: 1rem;
            align-content: start;
            width: 100%;
        }

        .result-card .stMarkdown p,
        .result-card .stMarkdown li,
        .result-card .stMarkdown div,
        .result-card .stMarkdown strong {
            color: var(--ink) !important;
        }

        .result-card .stMarkdown,
        .result-card .stMarkdown p,
        .result-card .stMarkdown li,
        .result-card .stMarkdown ul,
        .result-card .stMarkdown ol,
        .result-card .stMarkdown table,
        .result-card .stMarkdown pre,
        .result-card .stMarkdown code {
            max-width: 100%;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .result-card .stMarkdown h1,
        .result-card .stMarkdown h2,
        .result-card .stMarkdown h3,
        .result-card .stMarkdown h4 {
            margin-top: 0.55rem;
            margin-bottom: 0.65rem;
            line-height: 1.15;
        }

        .result-card .stMarkdown ul,
        .result-card .stMarkdown ol {
            padding-left: 1.2rem;
        }

        .result-card .stMarkdown table {
            display: block;
            overflow-x: auto;
            border-collapse: collapse;
            border-radius: 16px;
            border: 1px solid var(--line);
            margin: 0.75rem 0;
        }

        .result-card .stMarkdown table th,
        .result-card .stMarkdown table td {
            min-width: 140px;
            padding: 0.7rem 0.8rem;
            border: 1px solid var(--line);
            text-align: left;
            vertical-align: top;
            color: var(--ink);
        }

        .result-card .stMarkdown table th {
            background: var(--table-head);
        }

        .stTable table {
            border-collapse: separate;
            border-spacing: 0;
            width: 100%;
            color: var(--ink);
            overflow: hidden;
            border-radius: 16px;
            table-layout: fixed;
        }

        .stTable thead tr th {
            background: var(--table-head);
            color: var(--ink);
            border-bottom: 1px solid var(--line);
            font-weight: 700;
            white-space: normal;
        }

        .stTable tbody tr td {
            background: transparent;
            color: var(--ink);
            border-bottom: 1px solid var(--line);
            vertical-align: top;
            white-space: normal;
            overflow-wrap: anywhere;
        }

        [data-testid="stAlert"] {
            border: 1px solid var(--line);
            border-radius: 16px;
            color: var(--ink);
            background: var(--surface);
        }

        code, pre {
            color: var(--ink) !important;
        }

        .stCodeBlock, .stCode {
            background: var(--input-bg) !important;
            border: 1px solid var(--line) !important;
            border-radius: 18px !important;
        }

        .results-shell {
            margin-top: 1rem;
            width: 100%;
        }

        .results-heading {
            margin: 0.2rem 0 1rem 0;
            color: var(--ink);
            font-size: 1.15rem;
            font-weight: 700;
        }

        .results-stack {
            display: grid;
            gap: 1rem;
            width: 100%;
            align-content: start;
        }

        @media (max-width: 900px) {
            .block-container {
                padding-top: 1.2rem;
                padding-left: 0.9rem;
                padding-right: 0.9rem;
            }

            .hero-shell {
                padding: 1.35rem 1rem 1.1rem 1rem;
            }

            .metric-row {
                grid-template-columns: 1fr;
            }

            .hero-title {
                font-size: clamp(2rem, 9vw, 2.7rem);
            }

            .section-card,
            .result-card {
                padding: 1rem;
                border-radius: 18px;
            }

            .result-card .stMarkdown table th,
            .result-card .stMarkdown table td {
                min-width: 120px;
                padding: 0.6rem 0.65rem;
            }
        }
        </style>
    """

    style = (
        style_template.replace("__PALETTE__", palette)
        .replace("__APP_BACKGROUND__", app_background)
        .replace("__HERO_BACKGROUND__", hero_background)
        .replace("__SIDEBAR_BACKGROUND__", sidebar_background)
    )

    st.markdown(
        style,
        unsafe_allow_html=True,
    )


def is_retriable(error):
    return isinstance(
        error,
        (
            google_exceptions.ServiceUnavailable,
            google_exceptions.DeadlineExceeded,
        ),
    )


if not hasattr(genai.GenerativeModel, "_original_generate_content"):
    original = getattr(
        genai.GenerativeModel.generate_content,
        "_target",
        genai.GenerativeModel.generate_content,
    )
    genai.GenerativeModel._original_generate_content = original

genai.GenerativeModel.generate_content = retry.Retry(predicate=is_retriable, timeout=15)(
    genai.GenerativeModel._original_generate_content
)

generation_config = {
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 40,
}

doc_prompt = """
You are a careful medical assistant. Analyze the symptoms or condition provided and offer a professional medical opinion with possible explanations, practical next steps, and conservative treatment guidance. Keep the tone clear and clinically grounded. Always include a safety reminder that the user should seek a licensed clinician for emergencies, severe symptoms, or medication decisions.
"""

structure_prompt = """
When given a medical condition, format the answer as follows:

1. Start with a short plain-language explanation of the condition.
2. Provide a table of prescription-only treatments only when they are commonly used and clearly note that a licensed clinician must prescribe them.
3. Provide a table of over-the-counter options if relevant.
4. Provide a table of home remedies or self-care measures if relevant.
5. End with bullet points for precautions and when to seek urgent care.

Use markdown tables with these headings:

### Prescription Treatments
| Medicine | Typical Use | Notes |
|----------|-------------|-------|

### OTC Options
| Medicine | Typical Use | Notes |
|----------|-------------|-------|

### Home Care
| Remedy | How It Helps | How To Use |
|--------|---------------|------------|
"""

combined_prompt = doc_prompt.strip() + "\n\n" + structure_prompt.strip()


def make_ddgs():
    try:
        return DDGS(backend="html")
    except TypeError:
        return DDGS()


@st.cache_data(ttl=3600, show_spinner=False)
def list_generatecontent_models():
    models = []
    try:
        for model in genai.list_models():
            supported = getattr(model, "supported_generation_methods", []) or []
            if "generateContent" in supported:
                name = getattr(model, "name", None)
                if name:
                    models.append(name.replace("models/", ""))
    except Exception:
        pass
    return sorted(set(models))


def pick_model_name(preferred=None):
    preferred = preferred or []
    available = list_generatecontent_models()

    for name in preferred:
        if name in available:
            return name

    common = [
        "gemini-flash-latest",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
    ]
    for name in common:
        if name in available:
            return name

    return available[0] if available else "gemini-1.5-flash"


def build_model(model_name: str):
    return genai.GenerativeModel(model_name=model_name, generation_config=generation_config)


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def retrieve_medical_data(query):
    try:
        with make_ddgs() as ddgs:
            last_err = None
            for attempt in range(3):
                try:
                    results = list(
                        ddgs.text(
                            query + " site:mayoclinic.org OR site:medlineplus.gov OR site:who.int",
                            max_results=2,
                        )
                        or []
                    )
                    last_err = None
                    break
                except Exception as err:
                    last_err = err
                    time.sleep(1.5 * (attempt + 1))
            if last_err:
                raise last_err

            docs = []
            sources = []
            for res in results:
                try:
                    url = res["href"]
                    page = requests.get(url, timeout=5)
                    soup = BeautifulSoup(page.text, "html.parser")
                    text = " ".join(p.get_text() for p in soup.find_all("p"))
                    if text:
                        docs.append(text[:2000])
                        sources.append(url)
                except Exception:
                    continue
            return "\n\n".join(docs), sources
    except DuckDuckGoSearchException:
        return "", []


def geocode_place(place: str):
    response = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": place, "format": "jsonv2", "limit": 1},
        headers={"User-Agent": "CliniGuideAI/1.0"},
        timeout=10,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    first = results[0]
    return {
        "lat": float(first["lat"]),
        "lon": float(first["lon"]),
        "label": first.get("display_name", place),
        "source": "manual",
    }


@st.cache_data(ttl=60 * 15, show_spinner=False)
def get_nearby_pharmacies(location):
    try:
        with make_ddgs() as ddgs:
            last_err = None
            for attempt in range(3):
                try:
                    results = list(ddgs.text(f"pharmacies near {location}", max_results=6) or [])
                    last_err = None
                    break
                except Exception as err:
                    last_err = err
                    time.sleep(1.5 * (attempt + 1))
            if last_err:
                raise last_err
            return [(r["title"], r["href"]) for r in results if "href" in r]
    except DuckDuckGoSearchException:
        return []


def render_shell():
    st.markdown(
        """
        <div class="hero-shell">
            <span class="eyebrow">Clinical Decision Support</span>
            <h1 class="hero-title">CliniGuide AI</h1>
            <p class="hero-copy">
                A single workspace for symptom guidance, prescription extraction, and nearby pharmacy lookup.
                Upload a prescription image, describe the condition, and review the extracted medicines alongside AI-assisted medical guidance.
            </p>
            <div class="metric-row">
                <div class="metric-card"><strong>Symptom Review</strong><span>Condition analysis with optional web-backed citations.</span></div>
                <div class="metric-card"><strong>Prescription Extraction</strong><span>Use a vision model to structure handwritten medicines, dose clues, and verification warnings.</span></div>
                <div class="metric-card"><strong>Local Support</strong><span>Search for nearby pharmacies from the same interface.</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(model_name, available_models, default_model):
    st.sidebar.markdown("## Workspace Controls")
    st.sidebar.caption("Tune the assistant without leaving the dashboard.")
    theme_mode = st.sidebar.selectbox(
        "Theme",
        options=["Light", "Dark"],
        index=0 if st.session_state.get("theme_mode", "Light") == "Light" else 1,
    )
    st.session_state["theme_mode"] = theme_mode
    use_web = st.sidebar.checkbox("Use web citations", value=True)
    use_pharmacies = st.sidebar.checkbox("Search nearby pharmacies", value=True)
    show_raw_ocr = st.sidebar.checkbox("Show raw extracted text", value=True)
    selected_model = st.sidebar.selectbox(
        "Gemini model",
        options=available_models if available_models else [default_model],
        index=(
            available_models.index(model_name)
            if available_models and model_name in available_models
            else 0
        ),
        help="Pick another model if your API key lacks access to the current one.",
    )
    return theme_mode, use_web, use_pharmacies, show_raw_ocr, selected_model


def render_ocr_results(ocr_payload, show_raw_ocr):
    st.markdown('<div class="result-card">', unsafe_allow_html=True)
    st.markdown('<span class="panel-kicker">Prescription</span>', unsafe_allow_html=True)
    st.markdown('<div class="result-title">Prescription Extraction Summary</div>', unsafe_allow_html=True)

    medicines = ocr_payload.get("medicines", [])
    if medicines:
        st.table(
            [
                {
                    "Medicine": med.get("name", "N/A"),
                    "Confidence": str(med.get("confidence", "low")).upper(),
                    "Dosage": med.get("dosage") or "N/A",
                    "Frequency": med.get("frequency") or "N/A",
                    "Duration": med.get("duration") or "N/A",
                    "Instructions": med.get("instructions") or "Verify manually",
                    "Red Flags": ", ".join(med.get("red_flags") or []) or "None",
                }
                for med in medicines
            ]
        )
    else:
        st.info("No medicine lines were confidently extracted from the image.")

    sectioned_output = ocr_payload.get("sectioned_output", {})
    if sectioned_output.get("usage_guidance"):
        st.markdown("**Verification guidance**")
        st.markdown(sectioned_output["usage_guidance"])

    if sectioned_output.get("extraction_warnings"):
        st.markdown("**Model warnings**")
        st.markdown(sectioned_output["extraction_warnings"])

    if sectioned_output.get("quality_gate"):
        st.markdown("**Quality gate**")
        st.markdown(sectioned_output["quality_gate"])

    if show_raw_ocr and ocr_payload.get("raw_text"):
        st.markdown("**Raw extracted text**")
        st.code(ocr_payload["raw_text"], language="text")

    st.markdown("</div>", unsafe_allow_html=True)


def generate_medical_response(condition, rag_text, rag_sources, model, model_name):
    if rag_text:
        full_prompt = (
            "The following medical content was retrieved from trusted sources to enhance accuracy:\n\n"
            f"{rag_text}\n\n---\n\n{combined_prompt}\n\nCondition: {condition}"
        )
    else:
        full_prompt = f"{combined_prompt}\n\nCondition: {condition}"

    if st.session_state.get("_model_name") != model_name:
        st.session_state.chat = model.start_chat(history=[])
        st.session_state["_model_name"] = model_name

    response = st.session_state.chat.send_message(full_prompt)

    st.markdown('<div class="result-card">', unsafe_allow_html=True)
    st.markdown('<span class="panel-kicker">Guidance</span>', unsafe_allow_html=True)
    st.markdown('<div class="result-title">Medical Guidance</div>', unsafe_allow_html=True)
    st.markdown(response.text)

    if rag_text and rag_sources:
        st.markdown("**Sources used**")
        st.markdown("\n".join(f"- [{url}]({url})" for url in rag_sources))
    elif not rag_text:
        st.info("Advice was generated without external citations because search results were unavailable or disabled.")

    st.markdown("</div>", unsafe_allow_html=True)


def render_pharmacies(location, use_pharmacies):
    if not use_pharmacies:
        return
    if not location:
        st.markdown('<div class="result-card">', unsafe_allow_html=True)
        st.markdown('<span class="panel-kicker">Local Support</span>', unsafe_allow_html=True)
        st.markdown('<div class="result-title">Nearby Pharmacies</div>', unsafe_allow_html=True)
        st.info("Enter a city or area to search nearby pharmacies.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    with st.spinner("Searching for nearby pharmacies..."):
        try:
            pharmacies = get_nearby_pharmacies(location)
        except Exception as err:
            pharmacies = []
            st.info(f"Nearby pharmacy lookup failed: {err}")

    st.markdown('<div class="result-card">', unsafe_allow_html=True)
    st.markdown('<span class="panel-kicker">Local Support</span>', unsafe_allow_html=True)
    st.markdown('<div class="result-title">Nearby Pharmacies</div>', unsafe_allow_html=True)
    if pharmacies:
        for name, link in pharmacies:
            st.markdown(f"- [{name}]({link})")
    else:
        st.info("No nearby pharmacies were found for the selected area.")
    st.markdown("</div>", unsafe_allow_html=True)


inject_styles(st.session_state.get("theme_mode", "Light"))
render_shell()

available_models = list_generatecontent_models()
default_model = pick_model_name(
    preferred=[os.getenv("GEMINI_MODEL", "")] if os.getenv("GEMINI_MODEL") else []
)
initial_model = default_model

theme_mode, use_web, use_pharmacies, show_raw_ocr, model_name = render_sidebar(
    initial_model, available_models, default_model
)

if theme_mode != st.session_state.get("_applied_theme"):
    st.session_state["_applied_theme"] = theme_mode
    st.rerun()

model = build_model(model_name)
if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])
    st.session_state["_model_name"] = model_name

left_col, right_col = st.columns([1.25, 1], gap="large")

with left_col:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<span class="panel-kicker">Step 1</span>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Condition Intake</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Describe the symptoms or diagnosis you want reviewed.</div>',
        unsafe_allow_html=True,
    )
    condition = st.text_area(
        "Condition",
        placeholder="Example: Fever, sore throat, cough, and body aches for 3 days.",
        height=150,
        label_visibility="collapsed",
    )
    location = st.text_input("Location", placeholder="Example: Delhi")
    st.markdown("</div>", unsafe_allow_html=True)

with right_col:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<span class="panel-kicker">Step 2</span>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Prescription Upload</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Upload a prescription image for model-assisted extraction and manual verification.</div>',
        unsafe_allow_html=True,
    )
    uploaded_file = st.file_uploader(
        "Prescription image",
        type=["png", "jpg", "jpeg", "webp"],
        label_visibility="collapsed",
    )
    st.markdown("</div>", unsafe_allow_html=True)

analyze = st.button("Analyze Condition And Prescription")

if analyze:
    if not condition and not uploaded_file:
        st.warning("Enter a condition or upload a prescription image to start.")
    else:
        rag_text, rag_sources = "", []
        ocr_payload = None

        if uploaded_file is not None:
            with st.spinner("Extracting medicines from the uploaded prescription..."):
                try:
                    ocr_payload = extract_prescription_from_bytes(
                        uploaded_file.getvalue(),
                        getattr(uploaded_file, "type", None),
                    )
                except ValueError as err:
                    st.error(f"Prescription input error: {err}")
                except Exception as err:
                    st.error(f"Failed to extract prescription text: {err}")

        if condition and use_web:
            with st.spinner("Retrieving medical references..."):
                rag_text, rag_sources = retrieve_medical_data(condition)
            if not rag_text:
                st.info(
                    "Web citations are temporarily unavailable. Continuing with model-only guidance."
                )

        st.markdown('<div class="results-shell"><div class="results-heading">Generated Review</div></div>', unsafe_allow_html=True)
        st.markdown('<div class="results-stack">', unsafe_allow_html=True)
        if condition:
            try:
                generate_medical_response(condition, rag_text, rag_sources, model, model_name)
            except Exception as err:
                msg = str(err)
                st.error(f"Error generating medical advice: {msg}")
                if any(
                    token in msg.lower()
                    for token in ["404", "429", "quota", "exhausted", "not found"]
                ):
                    st.warning(
                        "The selected Gemini model is unavailable for this API key or the quota is exhausted. Pick another model from the sidebar."
                    )

        if ocr_payload:
            render_ocr_results(ocr_payload, show_raw_ocr)

        render_pharmacies(location, use_pharmacies)
        st.markdown('</div>', unsafe_allow_html=True)

import streamlit as st
from dotenv import load_dotenv
import os
from google import generativeai as genai
from google.api_core import retry
import requests
from bs4 import BeautifulSoup
import test_geo as geo_locator  # Must return (name, link)
import folium

# Load environment variables
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

# Retry on API errors
is_retriable = lambda e: isinstance(e, genai.types.generation_types.APIError) and e.code in {429, 503}
genai.GenerativeModel.generate_content = retry.Retry(predicate=is_retriable)(genai.GenerativeModel.generate_content)

# Gemini model config
generation_config = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
}

# Prompts
doc_prompt = """
You are a highly experienced and specialized medical doctor with expertise in diagnosing diseases and prescribing appropriate treatments or medications. Please analyze the symptoms or condition provided and offer a professional medical opinion, including possible diagnoses and suggested treatments or medications. Ensure your advice is detailed, medically accurate, and based on current medical guidelines.
"""

structure_prompt = """
You are an expert medical doctor with years of experience in diagnosing and treating a wide range of diseases. When given any medical condition, your task is to:

1. Act as a real doctor and suggest **prescription medications** (including dosage, frequency, and duration) for the condition in a **well-structured table**.
2. Provide a separate table for **over-the-counter (OTC) medicines**, if applicable.
3. Provide a separate table for **effective home remedies**, including ingredients and instructions.
4. Provide a table listing **drugs NOT to take with the prescribed tablets** to avoid harmful interactions.
5. List **precautions and lifestyle advice** in bullet points to help manage or prevent the condition.

---

### 🩺 Prescription Medications

| Medicine Name | Dosage | Frequency | Duration | Notes |
|---------------|--------|-----------|----------|-------|
|               |        |           |          |       |

---

### 💊 OTC Medications (if applicable)

| Medicine Name | Dosage | Frequency | Duration | Notes |
|---------------|--------|-----------|----------|-------|
|               |        |           |          |       |

---

### 🏡 Home Remedies

| Remedy Name | Ingredients | Preparation Method | How to Use |
|-------------|-------------|--------------------|------------|
|             |             |                    |            |

---

### 🚫 Drugs NOT to Take With These Tablets

| Drug Name | Reason / Interaction Details |
|-----------|------------------------------|
|           |                              |

---

### ⚠️ Precautions and Lifestyle Advice

- Bullet point 1  
- Bullet point 2  
- Bullet point 3  
*(Add as many relevant points as needed)*

---

Start with a brief explanation of the disease in simple terms before diving into the tables. Be clear, professional, and helpful. Always include a safety reminder to consult a healthcare provider before starting any treatment.
"""

combined_prompt = doc_prompt.strip() + "\n\n" + structure_prompt.strip()

# RAG for medical data
def retrieve_medical_data(query):
    sources = ["https://www.mayoclinic.org", "https://medlineplus.gov", "https://www.who.int"]
    docs, urls = [], []
    for source in sources:
        try:
            url = f"{source}/search?q={query}"
            page = requests.get(url, timeout=5)
            text = BeautifulSoup(page.text, "html.parser").get_text()
            if text:
                docs.append(text[:2000])
                urls.append(url)
        except:
            continue
    return "\n\n".join(docs), urls

# Streamlit UI
st.set_page_config(page_title="AI Medical Assistant", layout="centered")
st.title("🧠 AI Medical Assistant")
st.markdown("Enter your medical condition and location to receive structured treatment advice and nearby pharmacies.")

# Initialize chat
model = genai.GenerativeModel(model_name="gemini-1.5-flash", generation_config=generation_config)
if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])

# Inputs
col1, col2 = st.columns(2)
with col1:
    condition = st.text_input("Enter medical condition (e.g., 'flu'):")
with col2:
    location = st.text_input("Enter your location (e.g., 'Mumbai'):")

# Main action
if st.button("Get Advice & Pharmacies") and condition:
    with st.spinner("Retrieving medical info..."):
        rag_text, rag_sources = retrieve_medical_data(condition)

    if rag_text:
        full_prompt = f"The following medical content was retrieved from trusted sources:\n\n{rag_text}\n\n{combined_prompt}\n\nCondition: {condition}"
        try:
            response = st.session_state.chat.send_message(full_prompt)
            st.markdown("### 🧠 Medical Advice")
            st.markdown(response.text)

            if rag_sources:
                st.markdown("### 🌐 Sources Used")
                for url in rag_sources:
                    st.markdown(f"- [{url}]({url})")
        except Exception as e:
            st.error(f"Gemini Error: {e}")
    else:
        st.warning("No medical content found for that condition.")

    if location:
        with st.spinner("Finding nearby pharmacies..."):
            pharmacies = geo_locator.find_medical_stores(location)

        if pharmacies:
            st.markdown("### 🏥 Nearby Pharmacies")
            for name, link in pharmacies:
                st.markdown(f"- [{name}]({link})")

            st.markdown("### 🗺️ Map of Nearby Pharmacies")
            with open("medical_stores_map.html", "r", encoding="utf-8") as f:
                st.components.v1.html(f.read(), height=500)
        else:
            st.warning("No pharmacies found in that location.")

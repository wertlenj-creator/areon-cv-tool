import streamlit as st
import requests
import json
import io
import time
from docxtpl import DocxTemplate, RichText
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📄")

API_KEY = st.secrets.get("GOOGLE_API_KEY", "")

def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def get_ai_data_direct(cv_text, user_notes):
    # TOTO JE TEN SPRÁVNY MODEL.
    # V diagnostike si ho mal. Fungoval, len bol preťažený.
    # Má limit zadarmo, na rozdiel od verzie 2.5.
    target_model = "gemini-2.0-flash"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={API_KEY}"
    headers = {"Content-Type": "application/json"}

    system_instruction = """
    Správaš sa ako senior HR špecialista pre Areon. Priprav dáta pre nemecký profil kandidáta.
    VÝSTUP MUSÍ BYŤ LEN ČISTÝ JSON (bez ```json).
    """
    
    final_prompt = f"{system_instruction}\nPoznámky: {user_notes}\nCV Text:\n{cv_text}"
    payload = {"contents": [{"parts": [{"text": final_prompt}]}]}

    # Skúsime to poslať až 3-krát, ak by bol Google preťažený
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            
            # Ak je všetko OK (200)
            if response.status_code == 200:
                result_json = response.json()
                try:
                    raw_text = result_json['candidates'][0]['content']['parts'][0]['text']
                    clean_json = raw_text.replace("```json", "").replace("```", "").strip()
                    data = json.loads(clean_json)

                    # RichText úprava pre Word
                    if "experience" in data:
                        for job in data["experience"]:
                            full_text = ""
                            if "details" in job and isinstance(job["details"], list):
                                for item in job["details"]:
                                    clean_item = str(item).strip()
                                    full_text += f"      o  {clean_item}\n"
                            job["details_flat"] = RichText(full_text.rstrip())
                    
                    return data # Úspech!
                
                except (KeyError, IndexError, json.JSONDecodeError):
                    st.error("Google vrátil nečitateľnú odpoveď.")
                    return None

            # Ak je preťažený (429)
            elif response.status_code == 429:
                wait_time = 10 # Počkáme 10 sekúnd
                st.warning(f"⚠️ Model je preťažený. Čakám {wait_time} sekúnd a skúsim to znova... (Pokus {attempt+1}/{max_retries})")
                time.sleep(wait_time)
                continue # Ideme na ďalší pokus
            
            # Iná chyba (napr. 404 alebo 400)
            else:
                st.error(f"❌ Chyba Google ({response.status_code}): {response.text}")
                return None

        except Exception as e:
            st.error(f"Kritická chyba pripojenia: {e}")
            return None

    st.error("❌ Nepodarilo sa získať dáta ani po opakovaných pokusoch.")
    return None

def generate_word(data, template_file):
    doc = DocxTemplate(template_file)
    doc.render(data)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

# --- UI ---
st.title("Generátor DE Profilov 🇩🇪")
st.caption(f"Verzia: Gemini 2.0 Flash (Direct)")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Nahraj PDF", type=["pdf"])
with col2:
    notes = st.text_area("Poznámky")

if uploaded_file and st.button("🚀 Vygenerovať", type="primary"):
    if not API_KEY:
        st.error("Chýba API kľúč!")
    else:
        with st.spinner("Spracovávam..."):
            text = extract_text_from_pdf(uploaded_file)
            data = get_ai_data_direct(text, notes)
            
            if data:
                try:
                    doc = generate_word(data, "template.docx")
                    st.success("Hotovo!")
                    safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                    st.download_button("📥 Stiahnuť Word", doc, f"Profil_{safe_name}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                except Exception as e:
                    st.error(f"Chyba Wordu: {e}")

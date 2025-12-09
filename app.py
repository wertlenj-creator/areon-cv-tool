import streamlit as st
import google.generativeai as genai
from docxtpl import DocxTemplate, RichText
import json
import io
import time
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📄")

# Načítanie API kľúča
api_key = st.secrets.get("GOOGLE_API_KEY", "")
if api_key:
    genai.configure(api_key=api_key)
else:
    st.error("Chýba API kľúč! Nastav GOOGLE_API_KEY v Secrets.")

def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def get_ai_data_safe(cv_text, user_notes):
    # TOTO JE KĽÚČOVÁ ZMENA:
    # Skúsime moderný model. Ak zlyhá (404), použijeme starý (gemini-pro).
    
    primary_model = "gemini-1.5-flash"
    fallback_model = "gemini-pro"   # Tento model existuje už dlho a funguje aj na starej knižnici

    system_prompt = """
    Správaš sa ako senior HR špecialista pre Areon. Priprav dáta pre nemecký profil kandidáta.
    VÝSTUP MUSÍ BYŤ LEN ČISTÝ JSON.
    
    PRAVIDLÁ:
    1. Jazyk výstupu: Nemčina (Business German).
    2. Školy/Odbory: Prelož do nemčiny.
    3. Firmy: Nechaj originál.
    4. Dátum narodenia: Ak chýba, odhadni rok (napr. "1990").
    5. Pohlavie: Muž = "Mann ♂", Žena = "Frau ♀".
    6. Formátovanie:
       - "details" v experience musí byť ZOZNAM (Array) stringov.
       - "languages" musí byť ZOZNAM (Array) stringov.
       - "skills" musí byť ZOZNAM (Array) stringov.
    
    JSON ŠTRUKTÚRA:
    {
        "personal": {
            "name": "Meno Priezvisko",
            "birth_date": "DD. Month YYYY",
            "nationality": "Nationalität (DE)",
            "gender": "Mann ♂ / Frau ♀"
        },
        "experience": [
            {
                "title": "Pozícia (DE)",
                "company": "Firma",
                "period": "MM/YYYY - MM/YYYY",
                "details": ["Bod 1", "Bod 2", "Bod 3"]
            }
        ],
        "education": [
             {
                "school": "Škola (DE)",
                "specialization": "Odbor (DE)",
                "period": "Rok - Rok",
                "location": "Mesto"
             }
        ],
        "languages": ["Jazyk 1", "Jazyk 2"],
        "skills": ["Skill 1", "Skill 2"]
    }
    """
    final_prompt = system_prompt + f"\nPoznámky: {user_notes}\nCV Text:\n{cv_text}"

    # --- POKUS 1: Moderný model ---
    try:
        model = genai.GenerativeModel(primary_model)
        response = model.generate_content(final_prompt)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
    
    except Exception as e:
        error_msg = str(e)
        # Ak dostaneme chybu 404 (Nenájdený), okamžite prepíname na zálohu
        if "404" in error_msg or "not found" in error_msg.lower() or "supported" in error_msg:
            st.warning(f"⚠️ Server používa staršiu verziu, prepínam na model '{fallback_model}'...")
            try:
                # --- POKUS 2: Starý model (Záloha) ---
                model = genai.GenerativeModel(fallback_model)
                response = model.generate_content(final_prompt)
                clean_json = response.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_json)
            except Exception as e2:
                st.error(f"❌ Zlyhal aj záložný model: {e2}")
                return None
        elif "429" in error_msg:
            st.error("❌ Vyčerpaný limit API kľúča (Quota exceeded).")
            return None
        else:
            st.error(f"❌ Chyba AI: {e}")
            return None

    # --- SPRACOVANIE DÁT PRE WORD ---
    if "experience" in data:
        for job in data["experience"]:
            full_text = ""
            if "details" in job and isinstance(job["details"], list):
                for item in job["details"]:
                    clean_item = str(item).strip()
                    full_text += f"      o  {clean_item}\n"
            job["details_flat"] = RichText(full_text.rstrip())
    
    return data

def generate_word(data, template_file):
    doc = DocxTemplate(template_file)
    doc.render(data)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

# --- UI ---
st.title("Generátor DE Profilov 🇩🇪")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Nahraj PDF", type=["pdf"])
with col2:
    notes = st.text_area("Poznámky")

if uploaded_file and st.button("🚀 Vygenerovať", type="primary"):
    with st.spinner("Pracujem..."):
        text = extract_text_from_pdf(uploaded_file)
        # Voláme funkciu SAFE, ktorá si poradí s chybou 404
        data = get_ai_data_safe(text, notes)
        
        if data:
            try:
                doc = generate_word(data, "template.docx")
                st.success("Hotovo!")
                safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                st.download_button("📥 Stiahnuť Word", doc, f"Profil_{safe_name}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            except Exception as e:
                st.error(f"Chyba Wordu: {e}")

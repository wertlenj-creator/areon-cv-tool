import streamlit as st
import requests  # <--- Toto nahrádza google-generativeai
import json
import io
import time
from docxtpl import DocxTemplate, RichText
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📄")

# Načítanie Kľúča
API_KEY = st.secrets.get("GOOGLE_API_KEY", "")
if not API_KEY:
    st.error("Chýba API kľúč! Nastav GOOGLE_API_KEY v Secrets.")

def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def get_ai_data_direct(cv_text, user_notes):
    """
    Táto funkcia obchádza Python knižnicu a volá Google priamo cez URL.
    Tým sa vyhneme chybám '404 not found' spôsobeným zlou inštaláciou.
    """
    
    # Použijeme model 1.5 Flash (najlepší pre Free tier)
    # Toto je priama adresa na Google server
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
    
    headers = {
        "Content-Type": "application/json"
    }

    # Prompt
    system_instruction = """
    Správaš sa ako senior HR špecialista pre Areon. Priprav dáta pre nemecký profil kandidáta.
    VÝSTUP MUSÍ BYŤ LEN ČISTÝ JSON (bez ```json značiek).
    
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
    
    final_prompt = f"{system_instruction}\nPoznámky: {user_notes}\nCV Text:\n{cv_text}"

    # Príprava dát pre odoslanie
    payload = {
        "contents": [{
            "parts": [{"text": final_prompt}]
        }]
    }

    try:
        # Odoslanie požiadavky (Requests POST)
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        # Kontrola odpovede
        if response.status_code != 200:
            st.error(f"Chyba komunikácie s Google: {response.status_code}")
            st.code(response.text) # Vypíše detail chyby
            return None

        # Spracovanie výsledku
        result_json = response.json()
        
        # Vytiahnutie textu z tej zložitej Google odpovede
        try:
            raw_text = result_json['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            st.error("Google vrátil prázdnu odpoveď (pravdepodobne blokovanie obsahu).")
            return None

        # Čistenie JSONu
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)

        # --- PRÍPRAVA PRE WORD (RichText) ---
        if "experience" in data:
            for job in data["experience"]:
                full_text = ""
                if "details" in job and isinstance(job["details"], list):
                    for item in job["details"]:
                        clean_item = str(item).strip()
                        full_text += f"      o  {clean_item}\n"
                job["details_flat"] = RichText(full_text.rstrip())
        
        return data

    except Exception as e:
        st.error(f"Kritická chyba: {e}")
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
st.caption("Verzia: Direct Connect (Bypass Library)")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Nahraj PDF", type=["pdf"])
with col2:
    notes = st.text_area("Poznámky")

if uploaded_file and st.button("🚀 Vygenerovať", type="primary"):
    with st.spinner("Pripájam sa na Google Direct API..."):
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

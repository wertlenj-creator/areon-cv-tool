import streamlit as st
import requests
import json
import io
from docxtpl import DocxTemplate, RichText
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📄")

# Načítanie API kľúča
API_KEY = st.secrets.get("GOOGLE_API_KEY", "")

def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def get_ai_data_direct(cv_text, user_notes):
    """
    Funkcia volá Google Gemini (1.5 Flash) priamo cez REST API.
    Obchádza problémy s knižnicou a generuje formátovanie pre Word s Tabulátormi.
    """
    
    # Použijeme gemini-1.5-flash (Najlepšie limity pre Free verziu)
    model_name = "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    
    headers = {"Content-Type": "application/json"}

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

    payload = {
        "contents": [{"parts": [{"text": final_prompt}]}]
    }

    try:
        # Odoslanie požiadavky na Google
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        # Ak zlyhá 1.5-flash (napr. 404), skúsime záložný starší model gemini-pro
        if response.status_code != 200:
            # st.warning(f"Primárny model neodpovedá ({response.status_code}), skúšam záložný...")
            url_backup = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={API_KEY}"
            response = requests.post(url_backup, headers=headers, data=json.dumps(payload))
            
            if response.status_code != 200:
                st.error(f"❌ Chyba Google ({response.status_code}): {response.text}")
                return None

        result_json = response.json()
        
        # Bezpečné získanie textu
        try:
            raw_text = result_json['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            st.error("Google vrátil prázdnu odpoveď (Safety Block).")
            return None

        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)

        # --- PRÍPRAVA PRE WORD (ZMENA ODRÁŽOK NA TABULÁTORY) ---
        if "experience" in data:
            for job in data["experience"]:
                full_text = ""
                if "details" in job and isinstance(job["details"], list):
                    for item in job["details"]:
                        clean_item = str(item).strip()
                        # TOTO JE TÁ ZMENA:
                        # • = Odrážka
                        # \t = Tabulátor (skočí na značku v pravítku)
                        full_text += f"•\t{clean_item}\n"
                
                # RichText zabezpečí, že Word pochopí špeciálne znaky
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

# --- UI APLIKÁCIE ---
st.title("Generátor DE Profilov 🇩🇪")
st.caption("Verzia: Direct API + Tabulátory")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Nahraj PDF", type=["pdf"])
with col2:
    notes = st.text_area("Poznámky", placeholder="Doplňujúce info...")

if uploaded_file and st.button("🚀 Vygenerovať", type="primary"):
    if not API_KEY:
        st.error("Chýba API kľúč!")
    else:
        with st.spinner("Pracujem..."):
            text = extract_text_from_pdf(uploaded_file)
            data = get_ai_data_direct(text, notes)
            
            if data:
                try:
                    doc = generate_word(data, "template.docx")
                    st.success("Hotovo!")
                    safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                    st.download_button(
                        label="📥 Stiahnuť Word", 
                        data=doc, 
                        file_name=f"Profil_{safe_name}.docx", 
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                except Exception as e:
                    st.error(f"Chyba pri tvorbe Wordu: {e}")

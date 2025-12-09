import streamlit as st
import google.generativeai as genai
from docxtpl import DocxTemplate, RichText
import json
import io
import time  # <--- Pridané pre časovač
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📄")

# Načítanie API kľúča
if "GOOGLE_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
else:
    st.error("Chýba API kľúč! Nastav GOOGLE_API_KEY v Secrets.")

def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def get_ai_data(cv_text, user_notes):
    # Model gemini-flash-latest je super, ale má limit 5 žiadostí/minútu
    model = genai.GenerativeModel('gemini-flash-latest')
    
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
    
    Poznámky: {notes}
    CV Text:
    """
    
    final_prompt = system_prompt.replace("{notes}", user_notes) + "\n" + cv_text
    
    # --- NOVINKA: AUTOMATICKÉ OPAKOVANIE PRI PREŤAŽENÍ ---
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(final_prompt)
            clean_json = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)

            # --- PRÍPRAVA TEXTU PRE WORD (RichText) ---
            if "experience" in data:
                for job in data["experience"]:
                    full_text = ""
                    if "details" in job and isinstance(job["details"], list):
                        for item in job["details"]:
                            clean_item = str(item).strip()
                            full_text += f"      o  {clean_item}\n"
                    
                    job["details_flat"] = RichText(full_text.rstrip())
            
            return data # Úspech! Vrátime dáta.

        except Exception as e:
            # Ak je to chyba 429 (Preťaženie), počkáme a skúsime znova
            if "429" in str(e):
                wait_time = 35 # Pre istotu 35 sekúnd
                st.warning(f"⚠️ Google AI je vyťažené (Speed Limit). Čakám {wait_time} sekúnd a skúsim to znova automaticky... (Pokus {attempt+1}/{max_retries})")
                time.sleep(wait_time)
                continue # Ide sa na ďalší pokus
            else:
                # Iná chyba - vypíšeme ju a končíme
                st.error(f"Chyba AI: {e}")
                return None
    
    st.error("Nepodarilo sa vygenerovať profil ani na 3 pokusy. Skús to neskôr.")
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
col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Nahraj PDF", type=["pdf"])
with col2:
    notes = st.text_area("Poznámky", placeholder="Napr. doplň vodičák sk. B...")

if uploaded_file and st.button("🚀 Vygenerovať", type="primary"):
    with st.spinner("Pracujem... (Ak to trvá dlhšie, čakám na uvoľnenie AI kapacity)"):
        text = extract_text_from_pdf(uploaded_file)
        data = get_ai_data(text, notes)
        if data:
            try:
                doc = generate_word(data, "template.docx")
                st.success("Hotovo!")
                
                safe_name = data['personal'].get('name', 'Kandidat').replace(' ', '_')
                
                st.download_button(
                    label="📥 Stiahnuť Word", 
                    data=doc, 
                    file_name=f"Profil_{safe_name}.docx", 
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            except Exception as e:
                st.error(f"Chyba pri tvorbe Wordu (Template): {e}")

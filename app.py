import streamlit as st
import google.generativeai as genai
from docxtpl import DocxTemplate
import json
import io
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
    # --- ZMENA: Používame model, ktorý sme našli v diagnostike ---
    model = genai.GenerativeModel('gemini-2.0-flash') 
    
    system_prompt = """
    Správaš sa ako senior HR špecialista pre Areon. Priprav dáta pre nemecký profil kandidáta.
    
    VÝSTUP MUSÍ BYŤ LEN ČISTÝ JSON.
    
    PRAVIDLÁ:
    1. Jazyk výstupu: Nemčina (Business German).
    2. Školy/Odbory: Prelož do nemčiny.
    3. Firmy: Nechaj originál.
    4. Dátum narodenia: Ak chýba, odhadni rok (napr. "1990") podľa praxe/školy.
    5. Pohlavie: Urči podľa mena. Muž = "Mann ♂", Žena = "Frau ♀".
    6. Formátovanie:
       - "details" v experience musí byť ZOZNAM (Array) viet.
       - "languages" musí byť ZOZNAM (Array) stringov "Jazyk - Úroveň".
       - "skills" musí byť ZOZNAM (Array) mixu hard/soft skills.
    
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
                "details": ["Bod 1 (DE)", "Bod 2 (DE)", "Bod 3 (DE)"]
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
        "languages": ["Jazyk 1 - Úroveň", "Jazyk 2 - Úroveň"],
        "skills": ["Skill 1", "Skill 2", "Skill 3"]
    }
    
    Poznámky recruitera: {notes}
    CV Text:
    """
    
    final_prompt = system_prompt.replace("{notes}", user_notes) + "\n" + cv_text
    
    try:
        response = model.generate_content(final_prompt)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"Chyba AI: {e}")
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
    with st.spinner("Pracujem..."):
        text = extract_text_from_pdf(uploaded_file)
        data = get_ai_data(text, notes)
        if data:
            try:
                doc = generate_word(data, "template.docx")
                st.success("Hotovo!")
                
                # Vytvorenie názvu súboru
                safe_name = data['personal'].get('name', 'Kandidat').replace(' ', '_')
                
                st.download_button(
                    label="📥 Stiahnuť Word", 
                    data=doc, 
                    file_name=f"Profil_{safe_name}.docx", 
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            except Exception as e:
                st.error(f"Chyba pri tvorbe Wordu (Template): {e}")

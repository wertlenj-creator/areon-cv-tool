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

def get_ai_data_robust(cv_text, user_notes):
    """
    Skúša rad za radom rôzne modely podľa toho, čo je dostupné.
    Zoznam je zoradený podľa tvojej diagnostiky.
    """
    
    # ZOZNAM MODELOV (Priorita podľa tvojej diagnostiky)
    candidate_models = [
        "gemini-2.0-flash",        # Nový, rýchly model (bol v tvojom zozname)
        "gemini-2.0-flash-exp",    # Záloha pre verziu 2.0
        "gemini-1.5-pro-latest",   # Silný Pro model
        "gemini-flash-latest",     # (Tento hádzal limit, je až ako 4. možnosť)
        "gemini-pro"               # Stará klasika (istota)
    ]

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

    # --- HLAVNÁ SLUČKA (Skúšame modely) ---
    for model_name in candidate_models:
        try:
            # st.write(f"🔧 Skúšam model: {model_name}...") # Debug (odkomentuj ak chceš vidieť proces)
            model = genai.GenerativeModel(model_name)
            
            # Skúsime vygenerovať obsah
            response = model.generate_content(final_prompt)
            
            # Ak sme tu, model fungoval! Spracujeme dáta.
            clean_json = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)

            # --- PRÍPRAVA TEXTU PRE WORD (RichText - Riešenie medzier) ---
            if "experience" in data:
                for job in data["experience"]:
                    full_text = ""
                    if "details" in job and isinstance(job["details"], list):
                        for item in job["details"]:
                            clean_item = str(item).strip()
                            # 6 medzier simuluje odsadenie, 'o' je odrážka
                            full_text += f"      o  {clean_item}\n"
                    
                    # RichText zabezpečí, že Word pochopí nové riadky
                    job["details_flat"] = RichText(full_text.rstrip())
            
            return data # HOTOVO, vraciame dáta a končíme.

        except Exception as e:
            error_msg = str(e)
            
            # 404 = Model neexistuje (ignorujeme a ideme ďalej)
            if "404" in error_msg or "not found" in error_msg.lower():
                continue 
            
            # 429 = Limit (počkáme a ideme na ďalší model)
            elif "429" in error_msg:
                st.warning(f"⚠️ Model {model_name} je momentálne preťažený. Prepínam na záložný model...")
                time.sleep(1) 
                continue
            
            else:
                # Iná chyba (napr. JSON error)
                st.error(f"Chyba pri modeli {model_name}: {e}")
                return None

    st.error("❌ Nepodarilo sa nájsť žiadny funkčný model. Skontroluj API kľúč alebo kvóty.")
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
    with st.spinner("Hľadám najlepší AI model a pracujem..."):
        text = extract_text_from_pdf(uploaded_file)
        
        # Voláme našu robustnú funkciu
        data = get_ai_data_robust(text, notes)
        
        if data:
            try:
                doc = generate_word(data, "template.docx")
                st.success("Hotovo! Profil je pripravený.")
                
                safe_name = data['personal'].get('name', 'Kandidat').replace(' ', '_')
                st.download_button(
                    label="📥 Stiahnuť Word", 
                    data=doc, 
                    file_name=f"Profil_{safe_name}.docx", 
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            except Exception as e:
                st.error(f"Chyba pri tvorbe Wordu: {e}")

import streamlit as st
import requests
import json
import io
from docxtpl import DocxTemplate, RichText
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📄")

# Načítanie OpenAI kľúča
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def get_ai_data_openai(cv_text, user_notes):
    # Použijeme gpt-4o-mini (Najlepší pomer cena/výkon pre tento účel)
    url = "https://api.openai.com/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    system_prompt = """
    Správaš sa ako senior HR špecialista pre Areon. Tvojou úlohou je extrahovať dáta z CV do nemeckého profilu.
    Odpovedaj IBA v JSON formáte.
    
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

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Poznámky: {user_notes}\nCV Text:\n{cv_text}"}
        ],
        "response_format": {"type": "json_object"}, # Zaručí bezchybný JSON
        "temperature": 0.2
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        if response.status_code != 200:
            st.error(f"❌ Chyba OpenAI ({response.status_code}): {response.text}")
            return None

        result = response.json()
        content = result['choices'][0]['message']['content']
        data = json.loads(content)

        # --- PRÍPRAVA PRE WORD (TABULÁTORY) ---
        # Aby to sedelo s tvojím nastavením "Hanging Indent" vo Worde
        if "experience" in data:
            for job in data["experience"]:
                full_text = ""
                if "details" in job and isinstance(job["details"], list):
                    for item in job["details"]:
                        clean_item = str(item).strip()
                        # Odrážka + Tabulátor (Word to zarovná podľa pravítka)
                        full_text += f"•\t{clean_item}\n"
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
st.caption("Verzia: OpenAI GPT-4o Mini (Stable)")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Nahraj PDF", type=["pdf"])
with col2:
    notes = st.text_area("Poznámky")

if uploaded_file and st.button("🚀 Vygenerovať", type="primary"):
    if not API_KEY:
        st.error("Chýba API kľúč! Nastav 'OPENAI_API_KEY' v Secrets.")
    else:
        with st.spinner("OpenAI pracuje..."):
            text = extract_text_from_pdf(uploaded_file)
            data = get_ai_data_openai(text, notes)
            
            if data:
                try:
                    doc = generate_word(data, "template.docx")
                    st.success("Hotovo!")
                    safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                    st.download_button("📥 Stiahnuť Word", doc, f"Profil_{safe_name}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                except Exception as e:
                    st.error(f"Chyba Wordu: {e}")

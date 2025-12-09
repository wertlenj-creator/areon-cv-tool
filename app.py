import streamlit as st
import requests
import json
import io
import time
from docxtpl import DocxTemplate, RichText
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📄")

# --- SIDEBAR: VÝBER MODELU ---
st.sidebar.header("⚙️ Nastavenia")
provider = st.sidebar.radio("Poskytovateľ AI:", ["Google Gemini (Free)", "OpenAI (Platené)"])

if provider == "Google Gemini (Free)":
    api_key = st.secrets.get("GOOGLE_API_KEY", "")
    # Zoznam všetkých možných modelov na testovanie
    model_options = [
        "gemini-1.5-flash",       # Štandard (Najlepší)
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash-001",
        "gemini-1.5-pro",
        "gemini-2.0-flash-exp",   # Experimentálny
        "gemini-pro"              # Starý
    ]
    selected_model = st.sidebar.selectbox("Vyber model:", model_options)
    
else:
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    selected_model = "gpt-4o-mini" # Lacný a rýchly model od OpenAI
    st.sidebar.info("Vyžaduje OPENAI_API_KEY v Secrets.")

# --- FUNKCIE ---

def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def get_ai_data(cv_text, user_notes, model_name, provider):
    
    system_prompt = """
    Správaš sa ako senior HR špecialista pre Areon. Priprav dáta pre nemecký profil kandidáta.
    VÝSTUP MUSÍ BYŤ LEN ČISTÝ JSON (bez ```json).
    
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
    final_prompt = f"{system_prompt}\nPoznámky: {user_notes}\nCV Text:\n{cv_text}"

    # --- LOGIKA PRE GOOGLE ---
    if provider == "Google Gemini (Free)":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": final_prompt}]}]}
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            
            if response.status_code != 200:
                st.error(f"❌ Chyba Google ({response.status_code}): {response.text}")
                return None
                
            result = response.json()
            raw_text = result['candidates'][0]['content']['parts'][0]['text']
            
        except Exception as e:
            st.error(f"Chyba pripojenia: {e}")
            return None

    # --- LOGIKA PRE OPENAI ---
    else:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Poznámky: {user_notes}\nCV Text:\n{cv_text}"}
            ],
            "response_format": {"type": "json_object"}
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            if response.status_code != 200:
                st.error(f"❌ Chyba OpenAI ({response.status_code}): {response.text}")
                return None
            result = response.json()
            raw_text = result['choices'][0]['message']['content']
        except Exception as e:
            st.error(f"Chyba pripojenia: {e}")
            return None

    # --- SPRACOVANIE JSON A WORD ---
    try:
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)

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
        st.error(f"Chyba pri čítaní dát z AI: {e}")
        return None

def generate_word(data, template_file):
    doc = DocxTemplate(template_file)
    doc.render(data)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

# --- UI HLAVNÉ OKNO ---
st.title("Generátor DE Profilov 🇩🇪")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Nahraj PDF", type=["pdf"])
with col2:
    notes = st.text_area("Poznámky")

if uploaded_file and st.button("🚀 Vygenerovať", type="primary"):
    if not api_key:
        st.error(f"Chyba: Chýba API kľúč pre {provider} v Secrets!")
    else:
        with st.spinner(f"Pracujem s modelom {selected_model}..."):
            text = extract_text_from_pdf(uploaded_file)
            data = get_ai_data(text, notes, selected_model, provider)
            
            if data:
                try:
                    doc = generate_word(data, "template.docx")
                    st.success("Hotovo!")
                    safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                    st.download_button("📥 Stiahnuť Word", doc, f"Profil_{safe_name}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                except Exception as e:
                    st.error(f"Chyba Wordu: {e}")

import streamlit as st
import requests
import json
import io
from docxtpl import DocxTemplate, RichText
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📄")

# Načítanie Google kľúča
API_KEY = st.secrets.get("GOOGLE_API_KEY", "")

def extract_text_from_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def get_ai_data_direct(cv_text, user_notes):
    # POUŽIJEME MODEL, KTORÝ TVOJ ÚČET POZNÁ (Podľa diagnostiky)
    # Ak máš platený účet, tento model nebude hádzať 429.
    model_name = "gemini-flash-latest"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    headers = {"Content-Type": "application/json"}

    system_instruction = """
    Správaš sa ako senior HR špecialista pre Areon. Priprav dáta pre nemecký profil kandidáta.
    VÝSTUP MUSÍ BYŤ LEN ČISTÝ JSON.
    """
    
    final_prompt = f"{system_instruction}\nPoznámky: {user_notes}\nCV Text:\n{cv_text}"

    payload = {
        "contents": [{"parts": [{"text": final_prompt}]}]
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        if response.status_code != 200:
            st.error(f"❌ Chyba Google ({response.status_code}): {response.text}")
            return None

        result_json = response.json()
        
        try:
            raw_text = result_json['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            st.error("Google vrátil prázdnu odpoveď.")
            return None

        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)

        # --- PRÍPRAVA PRE WORD (TABULÁTORY) ---
        if "experience" in data:
            for job in data["experience"]:
                full_text = ""
                if "details" in job and isinstance(job["details"], list):
                    for item in job["details"]:
                        clean_item = str(item).strip()
                        # Používame TABULÁTOR (\t) pre zarovnanie vo Worde
                        full_text += f"•\t{clean_item}\n"
                
                # Zabalíme do RichText - Word to pochopí
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
st.caption(f"Verzia: Gemini Flash Latest (Paid/High Limit)")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Nahraj PDF", type=["pdf"])
with col2:
    notes = st.text_area("Poznámky")

if uploaded_file and st.button("🚀 Vygenerovať", type="primary"):
    if not API_KEY:
        st.error("Chýba API kľúč! Skontroluj Secrets, či tam máš 'GOOGLE_API_KEY'.")
    else:
        with st.spinner("Generujem profil..."):
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

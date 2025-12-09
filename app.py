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

def get_ai_data_simple(cv_text, user_notes):
    # Používame IBA 1.5 Flash. Ak nefunguje tento, nefunguje nič.
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    system_prompt = """
    Správaš sa ako senior HR špecialista pre Areon. Priprav dáta pre nemecký profil kandidáta.
    VÝSTUP MUSÍ BYŤ LEN ČISTÝ JSON.
    """
    
    final_prompt = system_prompt + f"\nPoznámky: {user_notes}\nCV Text:\n{cv_text}"

    try:
        # Skúsime to raz a poriadne
        response = model.generate_content(final_prompt)
        
        # Spracovanie JSON
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)

        # RichText úprava
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
        # TOTO JE DÔLEŽITÉ: Vypíšeme SKUTOČNÚ chybu
        st.error(f"❌ KRITICKÁ CHYBA GOOGLE: {str(e)}")
        st.warning("Ak vidíš 'Invalid API Key', skontroluj Secrets. Ak vidíš '404', knižnica je stará. Ak vidíš '429', kľúč je vyčerpaný.")
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
st.caption("Verzia: Gemini 1.5 Flash (Single Mode)")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Nahraj PDF", type=["pdf"])
with col2:
    notes = st.text_area("Poznámky")

if uploaded_file and st.button("🚀 Vygenerovať", type="primary"):
    with st.spinner("Komunikujem s Google..."):
        text = extract_text_from_pdf(uploaded_file)
        data = get_ai_data_simple(text, notes)
        
        if data:
            try:
                doc = generate_word(data, "template.docx")
                st.success("Hotovo!")
                safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                st.download_button("📥 Stiahnuť Word", doc, f"Profil_{safe_name}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            except Exception as e:
                st.error(f"Chyba Wordu: {e}")

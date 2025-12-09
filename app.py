import streamlit as st
import requests
import json
import io
import zipfile
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
    """
    Táto funkcia získa dáta z OpenAI A ROVNO ich pripraví pre Word.
    Tým odľahčíme zvyšok kódu od zložitej logiky.
    """
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
        "response_format": {"type": "json_object"},
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
        
        # --- INTERNÁ ÚPRAVA PRE WORD (TABULÁTORY) ---
        # Robíme to už tu, aby sme nemuseli kopírovať kód v UI časti
        if "experience" in data:
            for job in data["experience"]:
                full_text = ""
                if "details" in job and isinstance(job["details"], list):
                    for item in job["details"]:
                        clean_item = str(item).strip()
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

# --- UI APLIKÁCIE ---
st.title("Generátor DE Profilov 🇩🇪")
st.caption("Verzia: OpenAI (Stable)")

col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader("Nahraj PDF (jedno alebo viac)", type=["pdf"], accept_multiple_files=True)

with col2:
    notes = st.text_area("Spoločné poznámky")

if uploaded_files:
    
    # --- SCENÁR A: JEDEN SÚBOR ---
    if len(uploaded_files) == 1:
        if st.button("🚀 Vygenerovať profil", type="primary"):
            if not API_KEY:
                st.error("Chýba OPENAI_API_KEY!")
            else:
                pdf_file = uploaded_files[0]
                with st.spinner(f"Spracovávam {pdf_file.name}..."):
                    text = extract_text_from_pdf(pdf_file)
                    data = get_ai_data_openai(text, notes) # Dáta už sú pripravené aj s formátovaním
                    
                    if data:
                        try:
                            doc = generate_word(data, "template.docx")
                            st.success("Hotovo!")
                            safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                            
                            st.download_button(
                                label="📥 Stiahnuť Word (.docx)",
                                data=doc,
                                file_name=f"Profil_{safe_name}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            )
                        except Exception as e:
                            st.error(f"Chyba pri tvorbe Wordu: {e}")

    # --- SCENÁR B: VIAC SÚBOROV (ZIP) ---
    else:
        if st.button(f"🚀 Vygenerovať balík ({len(uploaded_files)} profilov)", type="primary"):
            if not API_KEY:
                st.error("Chýba OPENAI_API_KEY!")
            else:
                zip_buffer = io.BytesIO()
                my_bar = st.progress(0, text="Začínam...")
                success_count = 0
                
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, pdf_file in enumerate(uploaded_files):
                        my_bar.progress((i) / len(uploaded_files), text=f"Spracovávam: {pdf_file.name}")
                        
                        try:
                            text = extract_text_from_pdf(pdf_file)
                            data = get_ai_data_openai(text, notes)
                            
                            if data:
                                doc_io = generate_word(data, "template.docx")
                                safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                                zf.writestr(f"Profil_{safe_name}.docx", doc_io.getvalue())
                                success_count += 1
                                st.write(f"✅ {safe_name}")
                            else:
                                st.error(f"❌ Chyba pri {pdf_file.name}")
                                
                        except Exception as e:
                            st.error(f"❌ Kritická chyba pri {pdf_file.name}: {e}")

                my_bar.progress(100, text="Hotovo!")
                
                if success_count > 0:
                    st.success(f"Hotovo! Spracovaných {success_count} súborov.")
                    st.download_button(
                        label="📦 Stiahnuť všetko (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name="Areon_Profily.zip",
                        mime="application/zip"
                    )

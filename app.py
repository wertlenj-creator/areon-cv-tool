import streamlit as st
import requests
import json
import io
import zipfile  # <--- Nová knižnica pre balenie do ZIP
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
st.caption("Verzia: Hromadný ZIP Export (OpenAI)")

col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader("Nahraj PDF (jedno alebo viac)", type=["pdf"], accept_multiple_files=True)

with col2:
    notes = st.text_area("Spoločné poznámky")

if uploaded_files and st.button(f"🚀 Vygenerovať balík ({len(uploaded_files)} profilov)", type="primary"):
    if not API_KEY:
        st.error("Chýba OPENAI_API_KEY v Secrets!")
    else:
        # Pripravíme si ZIP pamäť
        zip_buffer = io.BytesIO()
        
        # Ukazovateľ postupu (Progress bar)
        progress_text = "Spracovávam životopisy..."
        my_bar = st.progress(0, text=progress_text)
        
        success_count = 0
        
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            
            for i, pdf_file in enumerate(uploaded_files):
                # Aktualizácia progress baru
                my_bar.progress((i) / len(uploaded_files), text=f"Spracovávam: {pdf_file.name}")
                
                try:
                    # 1. Extrakcia
                    text = extract_text_from_pdf(pdf_file)
                    
                    # 2. AI Spracovanie
                    data = get_ai_data_openai(text, notes)
                    
                    if data:
                        # 3. RichText / Word formátovanie
                        if "experience" in data:
                            for job in data["experience"]:
                                full_text = ""
                                if "details" in job and isinstance(job["details"], list):
                                    for item in job["details"]:
                                        clean_item = str(item).strip()
                                        full_text += f"•\t{clean_item}\n"
                                job["details_flat"] = RichText(full_text.rstrip())

                        # 4. Generovanie Wordu
                        doc_io = generate_word(data, "template.docx")
                        
                        # 5. Pridanie do ZIPu
                        safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                        file_name_in_zip = f"Profil_{safe_name}.docx"
                        
                        # Pozor: ZipFile potrebuje 'bytes', nie 'BytesIO', preto .getvalue()
                        zf.writestr(file_name_in_zip, doc_io.getvalue())
                        
                        success_count += 1
                        st.write(f"✅ {safe_name} - Pripravený")
                    else:
                        st.error(f"❌ {pdf_file.name} - Chyba pri spracovaní")
                        
                except Exception as e:
                    st.error(f"❌ Kritická chyba pri {pdf_file.name}: {e}")

        # Hotovo
        my_bar.progress(100, text="Hotovo!")
        
        if success_count > 0:
            st.success(f"Úspešne spracovaných {success_count} z {len(uploaded_files)} profilov.")
            
            # Jedno tlačidlo na stiahnutie ZIPu
            st.download_button(
                label="📦 Stiahnuť všetky profily (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="Areon_Profily.zip",
                mime="application/zip"
            )

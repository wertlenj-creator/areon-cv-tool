import streamlit as st
import requests
import json
import io
import zipfile
import base64
from docxtpl import DocxTemplate, RichText
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📄")

# Načítanie OpenAI kľúča
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

# --- POMOCNÉ FUNKCIE ---

def extract_text_from_pdf(uploaded_file):
    """Vytiahne text z klasického PDF"""
    try:
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            extract = page.extract_text()
            if extract:
                text += extract + "\n"
        return text
    except Exception:
        return ""

def encode_image(uploaded_file):
    """Pripraví obrázok pre OpenAI (Base64)"""
    return base64.b64encode(uploaded_file.getvalue()).decode('utf-8')

def get_ai_data_openai(content, user_notes, is_image=False, mime_type="image/jpeg"):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    # --- INŠTRUKCIE ---
    system_prompt = """
    Správaš sa ako senior HR špecialista pre Areon. Tvojou úlohou je extrahovať dáta z CV do nemeckého profilu.
    Odpovedaj IBA v JSON formáte.
    
    ===========
    PRAVIDLÁ PRE SPRACOVANIE ÚDAJOV:

    1. JAZYKY (SPRACHKENNTNISSE) - PRÍSNE CEFR:
       - Tu a LEN TU používaj úrovne: A1, A2, B1, B2, C1, C2 alebo Muttersprache.
       - Prevod: Začiatočník=A1/A2, Mierne pokročilý=B1, Stredne=B2, Pokročilý=C1, Expert=C2.
       
       LOGIKA NÁRODNOSTI (Automatické doplnenie):
       A) Ak je SLOVÁK: Pridaj "Tschechisch – C1" a "Slowakisch – Muttersprache".
       B) Ak je ČECH: Pridaj "Slowakisch – C1" a "Tschechisch – Muttersprache".
       C) Ak je POLIAK: Pridaj "Polnisch – Muttersprache".
       *Rodný jazyk uvádzaj vždy ako posledný.*

    2. SKILLS (SONSTIGE FÄHIGKEITEN) - PRIRODZENÝ VÝPIS:
       - NEPRIDÁVAJ umelé hodnotenia (Gut, Sehr gut), ak v CV nie sú explicitne uvedené!
       - Ak v CV chýba úroveň, vypíš len názov zručnosti.
       - Ak je úroveň uvedená, prelož ju do nemčiny.

    3. RADENIE (CHRONOLÓGIA):
       - Vzdelanie a Skúsenosti zoraď od NAJNOVŠIEHO po najstaršie (2024 -> 2010).
       - Ignoruj poradie v pôvodnom súbore, zoraď to podľa dátumov.

    4. VŠEOBECNÉ:
       - Jazyk výstupu: Nemčina (Business German).
       - Školy/Odbory: Prelož do nemčiny.
       - Dátum narodenia: Ak chýba, odhadni rok.
       - Pohlavie: Muž = "Mann ♂", Žena = "Frau ♀".

    5. LOKALITA A KRAJINA (Dôležité):
       - Formát poľa "company" musí byť PRESNE: "Názov firmy, Mesto (KÓD KRAJINY)".
       - ZAKÁZANÉ: Neuvádzaj ulicu, číslo domu, ani PSČ! Len čisté mesto.
       - ZAKÁZANÉ: Neuvádzaj celý názov krajiny (nepíš "Deutschland", "Slowakei").
       - POVINNÉ: Použi len ISO kód v zátvorke (SK, DE, AT, CH, CZ, HU, PL...).
       - Kód krajiny si musíš DOMYSLIEŤ podľa mesta, ak tam nie je.
       
       Príklady SPRÁVNE:
       - "Volkswagen, Bratislava (SK)"
       - "Audi, Győr (HU)"
       - "BMW, München (DE)"
       
       Príklady NESPRÁVNE:
       - "Volkswagen, J. Jonáša 1, Bratislava" (Obsahuje ulicu)
       - "BMW, München, Deutschland" (Obsahuje celý názov krajiny)
    ===========
    
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
                "company": "Firma, Mesto (KÓD)",
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

    # --- PRÍPRAVA SPRÁVY PRE AI ---
    user_message_content = []

    text_instruction = f"Poznámky recruitera: {user_notes}\n"
    if not is_image:
        text_instruction += f"\nCV Text:\n{content}"
    else:
        text_instruction += "\nAnalyzuj priložený obrázok životopisu."

    user_message_content.append({"type": "text", "text": text_instruction})

    if is_image:
        user_message_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{content}",
                "detail": "high"
            }
        })

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message_content}
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
        content_resp = result['choices'][0]['message']['content']
        data = json.loads(content_resp)
        
        # --- ÚPRAVA PRE WORD (TABULÁTORY) ---
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
st.caption("Verzia: Final (No Streets, ISO Country Codes)")

col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader(
        "Nahraj súbory (PDF, JPG, PNG)", 
        type=["pdf", "jpg", "jpeg", "png"], 
        accept_multiple_files=True
    )

with col2:
    notes = st.text_area("Spoločné poznámky")

if uploaded_files:
    btn_text = "🚀 Vygenerovať profil" if len(uploaded_files) == 1 else f"🚀 Vygenerovať balík ({len(uploaded_files)})"
    
    if st.button(btn_text, type="primary"):
        if not API_KEY:
            st.error("Chýba OPENAI_API_KEY!")
        else:
            zip_buffer = io.BytesIO()
            results = []
            my_bar = st.progress(0, text="Začínam...")

            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for i, file in enumerate(uploaded_files):
                    my_bar.progress((i) / len(uploaded_files), text=f"Spracovávam: {file.name}")
                    
                    try:
                        data = None
                        if file.type == "application/pdf":
                            text = extract_text_from_pdf(file)
                            if not text.strip():
                                st.warning(f"⚠️ PDF {file.name} je asi sken. Skús JPG.")
                            data = get_ai_data_openai(text, notes, is_image=False)
                        
                        elif file.type in ["image/jpeg", "image/png", "image/jpg"]:
                            base64_img = encode_image(file)
                            data = get_ai_data_openai(base64_img, notes, is_image=True, mime_type=file.type)
                        
                        if data:
                            doc_io = generate_word(data, "template.docx")
                            safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                            filename_docx = f"Profil_{safe_name}.docx"
                            
                            zf.writestr(filename_docx, doc_io.getvalue())
                            results.append({"name": filename_docx, "data": doc_io.getvalue()})
                            
                            st.write(f"✅ {safe_name}")
                        else:
                            st.error(f"❌ Chyba pri {file.name}")

                    except Exception as e:
                        st.error(f"❌ Chyba: {e}")

            my_bar.progress(100, text="Hotovo!")

            if len(results) > 0:
                if len(uploaded_files) == 1:
                    st.download_button(
                        label="📥 Stiahnuť Word (.docx)",
                        data=results[0]["data"],
                        file_name=results[0]["name"],
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                else:
                    st.success(f"Spracovaných {len(results)} súborov.")
                    st.download_button(
                        label="📦 Stiahnuť všetko (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name="Areon_Profily.zip",
                        mime="application/zip"
                    )

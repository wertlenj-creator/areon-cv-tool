import streamlit as st
import requests
import json
import io
import zipfile
import base64
import unicodedata # <--- Nová knižnica pre odstraňovanie diakritiky
from datetime import datetime
from docxtpl import DocxTemplate, RichText
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📄")

# Načítanie OpenAI kľúča
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

# --- POMOCNÉ FUNKCIE ---

def remove_diacritics(text):
    """Odstráni dĺžne, mäkčene a iné akcenty z textu (napr. Čonka -> Conka)"""
    if not text:
        return ""
    # Normalizuje text na základné znaky a akcenty zvlášť, potom akcenty vymaže
    nfd_form = unicodedata.normalize('NFD', text)
    return u"".join([c for c in nfd_form if not unicodedata.combining(c)])

def extract_text_from_pdf(uploaded_file):
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
    return base64.b64encode(uploaded_file.getvalue()).decode('utf-8')

def get_ai_data_openai(content, user_notes, is_image=False, mime_type="image/jpeg"):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    system_prompt = """
    Správaš sa ako senior HR špecialista pre Areon. Tvojou úlohou je extrahovať dáta z CV do nemeckého profilu.
    Odpovedaj IBA v JSON formáte.
    
    ===========
    PRAVIDLÁ PRE SPRACOVANIE ÚDAJOV:

    1. JAZYKY (SPRACHKENNTNISSE) - PRÍSNE CEFR:
       - Tu a LEN TU používaj úrovne: A1, A2, B1, B2, C1, C2 alebo Muttersprache.
       - LOGIKA NÁRODNOSTI:
         A) Ak je SLOVÁK: Pridaj "Tschechisch – C1" a "Slowakisch – Muttersprache".
         B) Ak je ČECH: Pridaj "Slowakisch – C1" a "Tschechisch – Muttersprache".
         C) Ak je POLIAK: Pridaj "Polnisch – Muttersprache".
       *Rodný jazyk uvádzaj vždy ako posledný.*

    2. SKILLS (SONSTIGE FÄHIGKEITEN) - PRIRODZENÝ VÝPIS:
       - NEPRIDÁVAJ umelé hodnotenia (Gut, Sehr gut), ak v CV nie sú explicitne uvedené!
       - Ak v CV chýba úroveň, vypíš len názov zručnosti.
       - Ak je úroveň uvedená, prelož ju do nemčiny.

    3. RADENIE (CHRONOLÓGIA):
       - Vzdelanie a Skúsenosti zoraď od NAJNOVŠIEHO po najstaršie.

    4. VŠEOBECNÉ:
       - Jazyk výstupu: Nemčina (Business German).
       - Školy/Odbory: Prelož do nemčiny.
       - Firmy: Nechaj originál.
       - Dátum narodenia: Ak chýba, odhadni rok.
       - Pohlavie: Muž = "Mann ♂", Žena = "Frau ♀".
       - Nationality: Iba názov (napr. Slowakisch), bez jazykovej úrovne!
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
        
        # --- PRÍPRAVA DÁT PRE WORD (Odrážky, Meno, Dátum) ---
        
        if "experience" in data:
            for job in data["experience"]:
                full_text = ""
                if "details" in job and isinstance(job["details"], list):
                    for item in job["details"]:
                        clean_item = str(item).strip()
                        full_text += f"•\t{clean_item}\n"
                job["details_flat"] = RichText(full_text.rstrip())
        
        data["today"] = {"date": datetime.today().strftime("%d.%m.%Y")}
        
        full_name = data.get("personal", {}).get("name", "")
        name_parts = full_name.split(" ", 1) 
        first_name = name_parts[0] if len(name_parts) > 0 else full_name
        surname = name_parts[1] if len(name_parts) > 1 else ""
        
        data["personal"]["first_name"] = first_name
        data["personal"]["surname"] = surname
        
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
st.caption("Verzia: Multi-Template (Yanfeng File Naming)")

# --- VÝBER ŠABLÓNY ---
st.markdown("### 1. Nastavenia generovania")
template_choice = st.radio(
    "Vyber šablónu pre výsledný Word:",
    options=["Štandardná šablóna (Areon)", "Yanfeng šablóna (s tabuľkou)"],
    horizontal=True
)

if template_choice == "Štandardná šablóna (Areon)":
    selected_template_file = "template.docx"
else:
    selected_template_file = "template - Yanfeng.docx"

st.divider()

st.markdown("### 2. Nahraj životopisy")
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
                            doc_io = generate_word(data, selected_template_file)
                            
                            # --- LOGIKA PRE NÁZOV SÚBORU ---
                            first_name_raw = data.get('personal', {}).get('first_name', 'Kandidat')
                            surname_raw = data.get('personal', {}).get('surname', '')
                            
                            if template_choice == "Yanfeng šablóna (s tabuľkou)":
                                # Formát: Areon_Priezvisko_Meno (bez diakritiky a medzier)
                                clean_first = remove_diacritics(first_name_raw).replace(' ', '')
                                clean_surname = remove_diacritics(surname_raw).replace(' ', '')
                                
                                if clean_surname:
                                    filename_docx = f"Areon_{clean_surname}_{clean_first}.docx"
                                else:
                                    filename_docx = f"Areon_{clean_first}.docx"
                            else:
                                # Štandardný formát (zachová diakritiku)
                                safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                                filename_docx = f"Profil_{safe_name}.docx"
                            
                            zf.writestr(filename_docx, doc_io.getvalue())
                            results.append({"name": filename_docx, "data": doc_io.getvalue()})
                            
                            st.write(f"✅ Vytvorené: {filename_docx}")
                        else:
                            st.error(f"❌ Chyba pri {file.name}")

                    except Exception as e:
                        st.error(f"❌ Chyba: {e}")

            my_bar.progress(100, text="Hotovo!")

            if len(results) > 0:
                if len(uploaded_files) == 1:
                    st.download_button(
                        label=f"📥 Stiahnuť Word ({template_choice})",
                        data=results[0]["data"],
                        file_name=results[0]["name"],
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                else:
                    suffix = "Yanfeng" if "Yanfeng" in template_choice else "Standard"
                    st.success(f"Spracovaných {len(results)} súborov.")
                    st.download_button(
                        label=f"📦 Stiahnuť všetko (ZIP - {template_choice})",
                        data=zip_buffer.getvalue(),
                        file_name=f"Areon_Profily_{suffix}.zip",
                        mime="application/zip"
                    )

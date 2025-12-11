import streamlit as st
import requests
import json
import io
import zipfile
import base64
from docxtpl import DocxTemplate, RichText
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📝", layout="wide")

# Načítanie OpenAI kľúča
API_KEY = st.secrets.get("OPENAI_API_KEY", "")

# --- SESSION STATE INITIALIZATION ---
# Aby si appka pamätala dáta aj po kliknutí
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = {}
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False

# --- POMOCNÉ FUNKCIE ---

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

    # --- INŠTRUKCIE (AGRESÍVNY PREKLAD) ---
    system_prompt = """
    Správaš sa ako senior HR špecialista pre Areon. Tvojou úlohou je extrahovať dáta z CV do nemeckého profilu.
    Odpovedaj IBA v JSON formáte.
    
    ===========
    !!! KRITICKÉ PRAVIDLO PREKLADU !!!
    VŠETOK TEXT (okrem názvov firiem) MUSÍ BYŤ V NEMČINE (Business German).
    - Názvy pozícií: PRELOŽIŤ (napr. "Skladník" -> "Lagerarbeiter").
    - Popis práce: PRELOŽIŤ do profesionálnej nemčiny.
    - Názvy škôl a odborov: PRELOŽIŤ (napr. "Stredná odborná škola" -> "Mittlere Fachschule").
    - Ak je text v CV po slovensky/česky/anglicky -> PRELOŽ HO DO NEMČINY!
    ===========

    PRAVIDLÁ PRE ÚDAJE:

    1. JAZYKY (SPRACHKENNTNISSE) - CEFR:
       - Používaj úrovne: A1, A2, B1, B2, C1, C2 alebo Muttersprache.
       - LOGIKA NÁRODNOSTI:
         A) Ak je SLOVÁK: Pridaj "Tschechisch – C1", "Slowakisch – Muttersprache".
         B) Ak je ČECH: Pridaj "Slowakisch – C1", "Tschechisch – Muttersprache".
         C) Ak je POLIAK: Pridaj "Polnisch – Muttersprache".
       *Rodný jazyk uvádzaj vždy ako posledný.*

    2. SKILLS (SONSTIGE FÄHIGKEITEN):
       - Nepridávaj umelé hodnotenia (Gut, Sehr gut).
       - Vypíš len názov zručnosti (napr. "Microsoft Excel", "Teamfähigkeit").
       - Ak je úroveň uvedená v CV, prelož ju do nemčiny.

    3. LOKALITA A KRAJINA:
       - Formát company: "Názov firmy, Mesto (KÓD KRAJINY)".
       - Žiadne ulice, žiadne celé názvy krajín. Len ISO kód (SK, DE, AT...).

    4. RADENIE (CHRONOLÓGIA):
       - Vzdelanie a Skúsenosti zoraď od NAJNOVŠIEHO po najstaršie (2024 -> 2010).
       - Ignoruj poradie v pôvodnom súbore, zoraď to podľa dátumov.

    5. OSOBNÉ:
       - Nationalität: Len názov (napr. "Slowakisch"), žiadne "Muttersprache" sem nepatrí.
       - Meno: Zachovaj diakritiku.
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
                "title": "Pozícia (Preložené do DE)",
                "company": "Firma, Mesto (KÓD)",
                "period": "MM/YYYY - MM/YYYY",
                "details": ["Bod 1 (DE)", "Bod 2 (DE)"]
            }
        ],
        "education": [
             {
                "school": "Škola (Preložené do DE)",
                "specialization": "Odbor (Preložené do DE)",
                "period": "Rok - Rok",
                "location": "Mesto"
             }
        ],
        "languages": ["Jazyk 1", "Jazyk 2"],
        "skills": ["Skill 1", "Skill 2"]
    }
    """

    # --- PRÍPRAVA SPRÁVY ---
    user_message_content = []
    text_instruction = f"Poznámky recruitera: {user_notes}\n"
    
    if not is_image:
        text_instruction += f"\nCV Text na spracovanie:\n{content}"
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
            return None
        
        content_resp = response.json()['choices'][0]['message']['content']
        return json.loads(content_resp)

    except Exception:
        return None

def generate_word(data, template_file):
    # Príprava RichText pre Word pred generovaním
    if "experience" in data:
        for job in data["experience"]:
            full_text = ""
            if "details" in job and isinstance(job["details"], list):
                for item in job["details"]:
                    clean_item = str(item).strip()
                    full_text += f"•\t{clean_item}\n"
            job["details_flat"] = RichText(full_text.rstrip())
            
    doc = DocxTemplate(template_file)
    doc.render(data)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

# --- UI APLIKÁCIE ---
st.title("Generátor DE Profilov 🇩🇪")
st.caption("Verzia: Editor & Náhľad (v3.0)")

col1, col2 = st.columns([1, 2]) # Ľavý stĺpec užší, pravý širší

with col1:
    st.info("Krok 1: Nahraj súbory")
    uploaded_files = st.file_uploader(
        "Súbory (PDF, JPG, PNG)", 
        type=["pdf", "jpg", "jpeg", "png"], 
        accept_multiple_files=True
    )
    notes = st.text_area("Spoločné poznámky pre AI")
    
    # Tlačidlo ANALYZOVAŤ
    if uploaded_files and not st.session_state.analysis_done:
        if st.button(f"🔍 1. Analyzovať ({len(uploaded_files)}) súborov", type="primary"):
            if not API_KEY:
                st.error("Chýba OPENAI_API_KEY!")
            else:
                progress_bar = st.progress(0, text="Analyzujem životopisy...")
                
                for i, file in enumerate(uploaded_files):
                    progress_bar.progress((i)/len(uploaded_files), text=f"Analyzujem: {file.name}")
                    
                    # Spracovanie
                    try:
                        data = None
                        if file.type == "application/pdf":
                            text = extract_text_from_pdf(file)
                            data = get_ai_data_openai(text, notes, is_image=False)
                        elif file.type in ["image/jpeg", "image/png", "image/jpg"]:
                            b64 = encode_image(file)
                            data = get_ai_data_openai(b64, notes, is_image=True, mime_type=file.type)
                        
                        if data:
                            # Uložíme do session state pod menom súboru
                            st.session_state.processed_data[file.name] = data
                        else:
                            st.error(f"Chyba pri súbore {file.name}")
                            
                    except Exception as e:
                        st.error(f"Chyba: {e}")
                
                progress_bar.progress(100, text="Hotovo! Skontroluj dáta vpravo ->")
                st.session_state.analysis_done = True
                st.rerun() # Obnoví stránku aby sa ukázal editor

    # Tlačidlo RESET (ak chceš začať znova)
    if st.session_state.analysis_done:
        if st.button("🔄 Začať znova (Vymazať všetko)"):
            st.session_state.processed_data = {}
            st.session_state.analysis_done = False
            st.rerun()

# --- PRAVÝ STĹPEC (EDITOR) ---
with col2:
    if st.session_state.analysis_done and st.session_state.processed_data:
        st.success("✅ Analýza hotová. Skontroluj a uprav dáta pred generovaním.")
        st.divider()
        
        # Formulár pre hromadné stiahnutie
        with st.form("edit_form"):
            
            # Pre každý súbor vytvoríme rozbaľovacie okno (Expander)
            for filename, data in st.session_state.processed_data.items():
                candidate_name = data.get('personal', {}).get('name', 'Neznámy')
                
                with st.expander(f"👤 {candidate_name} ({filename})", expanded=False):
                    st.write("Tu môžeš opraviť údaje (JSON formát). Dávaj pozor na úvodzovky a čiarky!")
                    
                    # JSON Editor - tu môžeš prepisovať texty
                    edited_json = st.text_area(
                        f"Dáta pre: {filename}",
                        value=json.dumps(data, indent=4, ensure_ascii=False),
                        height=400,
                        key=f"editor_{filename}"
                    )
                    
                    # Uložíme zmenu späť do session state
                    try:
                        st.session_state.processed_data[filename] = json.loads(edited_json)
                    except json.JSONDecodeError:
                        st.error(f"❌ Chyba v syntaxi JSON pre {filename}! Oprav to.")

            st.divider()
            
            # Tlačidlo GENEROWAŤ WORDY
            submitted = st.form_submit_button("💾 2. Vygenerovať a Stiahnuť Wordy")
            
            if submitted:
                zip_buffer = io.BytesIO()
                cnt = 0
                
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for fname, final_data in st.session_state.processed_data.items():
                        try:
                            # Generovanie Wordu z upravených dát
                            doc_io = generate_word(final_data, "template.docx")
                            safe_name = final_data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                            zf.writestr(f"Profil_{safe_name}.docx", doc_io.getvalue())
                            cnt += 1
                        except Exception as e:
                            st.error(f"Chyba pri generovaní {fname}: {e}")
                
                if cnt > 0:
                    st.success(f"Vygenerovaných {cnt} profilov!")
                    st.download_button(
                        label="📦 STIAHNUŤ ZIP BALÍK",
                        data=zip_buffer.getvalue(),
                        file_name="Areon_Profily_Edited.zip",
                        mime="application/zip"
                    )

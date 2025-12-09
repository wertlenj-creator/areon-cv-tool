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
    """
    Univerzálna funkcia: Zvládne Text (z PDF) aj Obrázok (z JPG/PNG).
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
    7. RADENIE (Dôležité): Vzdelanie (education) aj Skúsenosti (experience) musia byť zoradené od NAJNOVŠIEHO po najstaršie (Reverse Chronological).
    
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

    # --- PRÍPRAVA SPRÁVY PRE AI ---
    user_message_content = []

    # 1. Pridáme inštrukcie a poznámky
    text_instruction = f"Poznámky recruitera: {user_notes}\n"
    if not is_image:
        text_instruction += f"\nCV Text:\n{content}"
    else:
        text_instruction += "\nAnalyzuj priložený obrázok životopisu."

    user_message_content.append({"type": "text", "text": text_instruction})

    # 2. Ak je to obrázok, pridáme ho do správy
    if is_image:
        user_message_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{content}",
                "detail": "high" # Aby AI čítala aj malé písmenká
            }
        })

    payload = {
        "model": "gpt-4o-mini", # Tento model má "oči" (Vision)
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
st.caption("Verzia: PDF + Obrázky (Vision) + Zoradenie")

col1, col2 = st.columns(2)
with col1:
    # ZMENA: Povolili sme aj obrázky
    uploaded_files = st.file_uploader(
        "Nahraj súbory (PDF, JPG, PNG)", 
        type=["pdf", "jpg", "jpeg", "png"], 
        accept_multiple_files=True
    )

with col2:
    notes = st.text_area("Spoločné poznámky")

# --- LOGIKA SPRACOVANIA ---
if uploaded_files:
    
    # Rozhodneme či tlačidlo pre jeden alebo pre balík
    btn_text = "🚀 Vygenerovať profil" if len(uploaded_files) == 1 else f"🚀 Vygenerovať balík ({len(uploaded_files)})"
    
    if st.button(btn_text, type="primary"):
        if not API_KEY:
            st.error("Chýba OPENAI_API_KEY!")
        else:
            # Príprava pre ZIP (ak bude viac súborov)
            zip_buffer = io.BytesIO()
            results = [] # Tu si uložíme úspešné dokumenty
            
            # Progress bar
            my_bar = st.progress(0, text="Začínam...")

            # --- CYKLUS CEZ SÚBORY ---
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for i, file in enumerate(uploaded_files):
                    my_bar.progress((i) / len(uploaded_files), text=f"Spracovávam: {file.name}")
                    
                    try:
                        data = None
                        
                        # A. Ak je to PDF
                        if file.type == "application/pdf":
                            text = extract_text_from_pdf(file)
                            # Ak je PDF prázdne (sken), skúsime ho poslať ako obrázok? 
                            if not text.strip():
                                st.warning(f"⚠️ PDF {file.name} vyzerá ako obrázok/sken. Ak výsledok nebude dobrý, skonvertuj ho na JPG.")
                            
                            data = get_ai_data_openai(text, notes, is_image=False)
                        
                        # B. Ak je to OBRÁZOK (JPG, PNG)
                        elif file.type in ["image/jpeg", "image/png", "image/jpg"]:
                            # Zakódujeme obrázok do base64
                            base64_img = encode_image(file)
                            data = get_ai_data_openai(base64_img, notes, is_image=True, mime_type=file.type)
                        
                        # C. Spracovanie výsledku
                        if data:
                            doc_io = generate_word(data, "template.docx")
                            safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                            filename_docx = f"Profil_{safe_name}.docx"
                            
                            # Uložíme do ZIPu
                            zf.writestr(filename_docx, doc_io.getvalue())
                            
                            # Uložíme si info pre single download
                            results.append({"name": filename_docx, "data": doc_io.getvalue()})
                            
                            st.write(f"✅ {safe_name}")
                        else:
                            st.error(f"❌ Chyba pri spracovaní {file.name}")

                    except Exception as e:
                        st.error(f"❌ Kritická chyba pri {file.name}: {e}")

            my_bar.progress(100, text="Hotovo!")

            # --- VÝSTUP (JEDEN vs VIAC) ---
            if len(results) > 0:
                # Ak bol len 1 súbor, ponúkneme priame stiahnutie .docx
                if len(uploaded_files) == 1:
                    st.download_button(
                        label="📥 Stiahnuť Word (.docx)",
                        data=results[0]["data"],
                        file_name=results[0]["name"],
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                # Ak bolo viac, ponúkneme ZIP
                else:
                    st.success(f"Spracovaných {len(results)} súborov.")
                    st.download_button(
                        label="📦 Stiahnuť všetko (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name="Areon_Profily.zip",
                        mime="application/zip"
                    )

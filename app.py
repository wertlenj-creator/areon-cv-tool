import streamlit as st
import requests
import json
import io
import zipfile
import base64
import unicodedata
from datetime import datetime
from docxtpl import DocxTemplate, RichText
from pypdf import PdfReader

# --- CONFIG ---
st.set_page_config(page_title="Areon CV Generator", page_icon="📄", layout="wide")

API_KEY = st.secrets.get("OPENAI_API_KEY", "")

# --- FIREMNÝ SLOVNÍK A PRAVIDLÁ (Zobrazený aj pre userov) ---
DICTIONARY_TEXT = """
**🏫 VZDELANIE (Školy):**
*   Základná škola = Grundschule
*   Stredná odborná škola / Učilište (SOŠ/SOU) = Berufsschule / Fachschule
*   Gymnázium = Gymnasium
*   Vysoká škola / Univerzita = Universität / Hochschule

**👷 PRACOVNÉ POZÍCIE:**
*   Skladník = Lagermitarbeiter / Fachkraft für Lagerlogistik
*   Vodič VZV / Vozíka = Gabelstaplerfahrer
*   Operátor výroby = Produktionsmitarbeiter / Anlagenführer
*   Zvárač = Schweißer
*   Vodič (kamión/dodávka) = Kraftfahrer / LKW-Fahrer

**🌍 KRAJINY A LOKALITY:**
*   AI automaticky dopĺňa kódy (SK, CZ, DE, AT, NL...).
*   Ak chýba mesto, AI sa riadi koncovkou firmy (GmbH = DE, B.V. = NL) alebo národnosťou kandidáta.

**💻 SKILLS (Zručnosti):**
*   PC znalosti (Word, Excel, PowerPoint) AI zlučuje do jedného bodu: "MS Office".
*   Soft skills (vlastnosti) sú obmedzené na max. 2 najdôležitejšie (napr. Teamfähigkeit).
"""

# --- POMOCNÉ FUNKCIE ---

def remove_diacritics(text):
    if not text: return ""
    nfd_form = unicodedata.normalize('NFD', text)
    return u"".join([c for c in nfd_form if not unicodedata.combining(c)])

def extract_text_from_pdf(uploaded_file):
    try:
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            extract = page.extract_text()
            if extract: text += extract + "\n"
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

    # --- TOP SECRET HR PROMPT ---
    system_prompt = """
    Správaš sa ako senior HR špecialista a nemecký native speaker pre Areon. 
    Extrahuj a prelož CV kandidáta. Odpovedaj IBA v JSON formáte.
    
    ===========
    0. POZNÁMKY RECRUITERA SÚ ABSOLÚTNE NADRADENÉ!
       - Ak poznámka prikazuje: vymazať prácu, predĺžiť roky, zmeniť dátum, doplniť VZV alebo inú zručnosť -> UROB TO PRESNE PODĽA POZNÁMKY a ignoruj v tomto bode pôvodné CV!

    1. JAZYKY (CEFR & NÁRODNOSŤ):
       - Hodnoť len: A1, A2, B1, B2, C1, C2, Muttersprache.
       - Ak je Slovák: Doplň "Tschechisch – C1" a "Slowakisch – Muttersprache".
       - Ak je Čech: Doplň "Slowakisch – C1" a "Tschechisch – Muttersprache".
       - Ak je Poliak: Doplň "Polnisch – Muttersprache".
       - Muttersprache daj vždy na koniec zoznamu.

    2. SKILLS A KOMPETENCIE (OPTIMALIZÁCIA):
       - IT a PC zručnosti: Ak má Word, Excel, PowerPoint, ZLÚČ ICH do jedného bodu "MS Office (Word, Excel)".
       - Hard Skills & Licencie (VZV, CNC, Zváranie...): Vypíš všetky relevantné.
       - Soft Skills: Vyber MAXIMÁLNE 2 najrelevantnejšie (napr. Teamfähigkeit, Flexibilität). Zbytočnú "vatu" vymaž.
       - Nepridávaj umelé hodnotenia (Gut, Sehr gut), pokiaľ nie sú v CV.

    3. FIRMY, KRAJINY A MESTÁ:
       - Formát: "Názov firmy, Mesto (KÓD KRAJINY)". ZÁKAZ písať ulice a celé názvy štátov.
       - Ak mesto chýba: 
         A) Ak má firma v názve GmbH, AG, KG -> Doplň (DE) alebo (AT).
         B) Ak má firma B.V. -> Doplň (NL).
         C) Ak znie lokálne, doplň podľa národnosti (Slovák = SK, Čech = CZ, Poliak = PL).

    4. POZÍCIE A ČINNOSTI (TOP GERMAN & DOMÝŠĽANIE):
       - Preklad musí byť v profi "Business German" (žiadne otrocké preklady slovo od slova).
       - POZÍCIE (Použi tento slovník): Skladník=Lagermitarbeiter, VZV=Gabelstaplerfahrer, Operátor=Produktionsmitarbeiter, Zvárač=Schweißer, Vodič=Kraftfahrer.
       - CHÝBAJÚCE ČINNOSTI: Ak je v CV uvedená len pozícia a firma, AUTOMATICKY VYMYSLI a doplň 2-3 typické pracovné úlohy pre danú pozíciu v danom priemysle (napr. pre Skladníka napíš: Príjem/výdaj tovaru, Práca so skenerom...).

    5. VZDELANIE A CHRONOLÓGIA:
       - Zoraď Vzdelanie a Prax REVERZNE CHRONOLOGICKY (Najnovšie hore!). Ignoruj poradie v CV.
       - ŠKOLY (Preklad): SOŠ/SOU=Berufsschule, Gymnázium=Gymnasium, VŠ=Universität/Hochschule, ZŠ=Grundschule.
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

    user_message_content = []
    text_instruction = f"POZNÁMKY (DÔLEŽITÉ): {user_notes}\n"
    if not is_image:
        text_instruction += f"\nCV Text:\n{content}"
    else:
        text_instruction += "\nAnalyzuj obrázok CV."

    user_message_content.append({"type": "text", "text": text_instruction})

    if is_image:
        user_message_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{content}", "detail": "high"}
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
            st.error(f"❌ Chyba OpenAI: {response.text}")
            return None
        return json.loads(response.json()['choices'][0]['message']['content'])
    except Exception as e:
        st.error(f"Kritická chyba: {e}")
        return None

def generate_word(data, template_file):
    # Formátovanie odrážok pre Word (Tabulátory)
    if "experience" in data:
        for job in data["experience"]:
            full_text = ""
            if "details" in job and isinstance(job["details"], list):
                for item in job["details"]:
                    clean_item = str(item).strip()
                    full_text += f"•\t{clean_item}\n"
            job["details_flat"] = RichText(full_text.rstrip())
    
    # Príprava mien a dátumu
    data["today"] = {"date": datetime.today().strftime("%d.%m.%Y")}
    full_name = data.get("personal", {}).get("name", "")
    name_parts = full_name.split(" ", 1) 
    data["personal"]["first_name"] = name_parts[0] if len(name_parts) > 0 else full_name
    data["personal"]["surname"] = name_parts[1] if len(name_parts) > 1 else ""

    doc = DocxTemplate(template_file)
    doc.render(data)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

# --- UI APLIKÁCIE ---

# Bočné menu
with st.sidebar:
    st.image("https://areon.sk/wp-content/uploads/2020/09/logo-areon-dark.svg", width=150)
    st.markdown("---")
    with st.expander("📚 Ako AI prekladá? (Slovník)"):
        st.markdown(DICTIONARY_TEXT)
    st.markdown("*Ak chceš upraviť slovník, kontaktuj admina.*")

# Hlavná časť
st.title("Generátor DE Profilov 🇩🇪")
st.caption("Verzia 4.0 (HR Profi & Auto-Complete)")

st.markdown("### 1. Šablóna")
template_choice = st.radio(
    "Vyber šablónu pre Word:",
    options=["Štandardná šablóna (Areon)", "Yanfeng šablóna (s tabuľkou)"],
    horizontal=True
)

selected_template_file = "template.docx" if template_choice == "Štandardná šablóna (Areon)" else "template - Yanfeng.docx"

st.divider()
st.markdown("### 2. Dáta")

col1, col2 = st.columns(2)
with col1:
    uploaded_files = st.file_uploader("Nahraj CV (PDF, JPG, PNG)", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True)
with col2:
    notes = st.text_area(
        "📝 Poznámky pre AI (Príkazy)", 
        placeholder="Napr: Vymaž brigádu v Tescu. Predĺž prácu v DHL do 2023. Doplň, že jazdil na VZV Retrak."
    )

if uploaded_files:
    btn_text = "🚀 Vygenerovať profil" if len(uploaded_files) == 1 else f"🚀 Vygenerovať balík ({len(uploaded_files)})"
    
    if st.button(btn_text, type="primary"):
        if not API_KEY:
            st.error("Chýba OPENAI_API_KEY v Secrets!")
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
                            data = get_ai_data_openai(text, notes, is_image=False)
                        else:
                            b64 = encode_image(file)
                            data = get_ai_data_openai(b64, notes, is_image=True, mime_type=file.type)
                        
                        if data:
                            doc_io = generate_word(data, selected_template_file)
                            
                            # Logika pomenovania
                            first_name = data.get('personal', {}).get('first_name', 'Kandidat')
                            surname = data.get('personal', {}).get('surname', '')
                            
                            if "Yanfeng" in selected_template_file:
                                clean_f = remove_diacritics(first_name).replace(' ', '')
                                clean_s = remove_diacritics(surname).replace(' ', '')
                                filename_docx = f"Areon_{clean_s}_{clean_f}.docx" if clean_s else f"Areon_{clean_f}.docx"
                            else:
                                safe_name = data.get('personal', {}).get('name', 'Kandidat').replace(' ', '_')
                                filename_docx = f"Profil_{safe_name}.docx"
                            
                            zf.writestr(filename_docx, doc_io.getvalue())
                            results.append({"name": filename_docx, "data": doc_io.getvalue()})
                            st.write(f"✅ Vytvorené: {filename_docx}")
                        else:
                            st.error(f"❌ Chyba AI pri {file.name}")

                    except Exception as e:
                        st.error(f"❌ Chyba aplikácie pri {file.name}: {e}")

            my_bar.progress(100, text="Hotovo!")

            if len(results) > 0:
                if len(uploaded_files) == 1:
                    st.download_button(
                        label=f"📥 Stiahnuť Word",
                        data=results[0]["data"],
                        file_name=results[0]["name"],
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                else:
                    st.success(f"Spracovaných {len(results)} súborov.")
                    st.download_button(
                        label=f"📦 Stiahnuť ZIP Balík",
                        data=zip_buffer.getvalue(),
                        file_name="Areon_Profily_Batch.zip",
                        mime="application/zip"
                    )

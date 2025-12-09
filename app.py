def get_ai_data(cv_text, user_notes):
    model = genai.GenerativeModel('gemini-flash-latest')
    
    system_prompt = """
    Správaš sa ako senior HR špecialista pre Areon. Priprav dáta pre nemecký profil kandidáta.
    
    VÝSTUP MUSÍ BYŤ LEN ČISTÝ JSON.
    
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
    
    Poznámky: {notes}
    CV Text:
    """
    
    final_prompt = system_prompt.replace("{notes}", user_notes) + "\n" + cv_text
    
    try:
        response = model.generate_content(final_prompt)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)

        # --- NOVÁ ČASŤ: PRÍPRAVA TEXTU PRE WORD (ABY NEBOLI MEDZERY) ---
        # Prejdeme všetky práce a vyrobíme "hotový text" pre detaily
        if "experience" in data:
            for job in data["experience"]:
                # Spojíme detaily do jedného textu s odrážkami
                # \n znamená nový riadok. "      o " simuluje odsadenie a guličku.
                # Používame RichText, aby Word chápal nové riadky
                full_text = ""
                if "details" in job and isinstance(job["details"], list):
                    for item in job["details"]:
                        # Tu si nastavíš medzery: 6 medzier pred 'o' spraví odsadenie
                        full_text += f"      o  {item}\n" 
                
                # Uložíme to do novej premennej 'details_flat'
                # .strip() na konci odstráni posledný prázdny riadok
                job["details_flat"] = full_text.rstrip()
        
        return data

    except Exception as e:
        st.error(f"Chyba AI: {e}")
        return None

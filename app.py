import streamlit as st
import google.generativeai as genai
import importlib.metadata
import os

st.title("🕵️ Diagnostika Servera")

# 1. KONTROLA VERZIE KNIŽNICE
try:
    version = importlib.metadata.version("google-generativeai")
    st.info(f"📦 Nainštalovaná verzia Google AI knižnice: **{version}**")
    # Nové modely vyžadujú verziu aspoň 0.5.0+, ideálne 0.8.3+
except Exception as e:
    st.error(f"Neviem zistiť verziu knižnice: {e}")

# 2. KONTROLA KĽÚČA
api_key = st.secrets.get("GOOGLE_API_KEY", "")
if api_key:
    st.success(f"🔑 Kľúč je načítaný (Dĺžka: {len(api_key)} znakov)")
    # Konfigurácia
    genai.configure(api_key=api_key)
else:
    st.error("❌ Kľúč sa nenašiel v Secrets!")

# 3. TEST DOSTUPNÝCH MODELOV (Toto je to najdôležitejšie)
st.write("---")
st.write("📡 Skúšam sa spojiť s Google a získať zoznam modelov...")

try:
    models = list(genai.list_models())
    st.success(f"✅ Spojenie úspešné! Tvoj kľúč vidí {len(models)} modelov.")
    
    st.write("👇 Zoznam modelov, ktoré môžeš použiť:")
    valid_models = []
    for m in models:
        # Vypíšeme len tie, ktoré vedia generovať text (generateContent)
        if 'generateContent' in m.supported_generation_methods:
            st.code(m.name)
            valid_models.append(m.name)
            
except Exception as e:
    st.error(f"❌ CHYBA pri spojení s Google: {e}")
    st.warning("Ak vidíš chybu 404 alebo PermissionDenied, problém je v API kľúči alebo regióne.")

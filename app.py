import streamlit as st
import numpy as np
from PIL import Image
import os
import io
import zipfile

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup - Precision V4", layout="wide")

# --- MAPPING COORDINATE (Calcolate sui tuoi file) ---
# Formato: "nome_file": (x_start_%, y_start_%, width_%, height_%)
TEMPLATE_MAPS = {
    "base_verticale_temi_app.jpg": (35.1, 10.4, 29.8, 79.2),
    "base_orizzontale_temi_app.jpg": (19.4, 9.4, 61.2, 81.2),
    "base_orizzontale_temi_app3.jpg": (19.4, 9.4, 61.2, 81.2),
    "base_quadrata_temi_app.jpg": (28.2, 10.4, 43.6, 77.4),
    "base_bottom_app.jpg": (22.8, 4.4, 54.8, 89.6),
    "base_copertina_verticale.jpg": (0, 0, 100, 100), # Fallback per piatti
}

def composite_precision(tmpl_pil, cover_pil, filename):
    # Carica template e crea versione grayscale per le ombre
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    
    # 1. Recupero coordinate dal Map
    if filename in TEMPLATE_MAPS:
        px, py, pw, ph = TEMPLATE_MAPS[filename]
        x1, y1 = int((px * w) / 100), int((py * h) / 100)
        tw, th = int((pw * w) / 100), int((ph * h) / 100)
    else:
        # Se non mappato, prova a coprire tutto o ignora
        return None

    # 2. Resize della cover
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # 3. Shadow Map (Effetto Moltiplica)
    # Prendiamo l'area del libro e la usiamo per dare realismo (rilegatura e pieghe)
    book_shadows = tmpl_gray[y1:y1+th, x1:x1+tw]
    # Normalizziamo: il bianco del mockup diventa 1.0 (trasparente), le ombre < 1.0
    shadow_map = np.clip(book_shadows / 250.0, 0, 1.0) 
    
    # 4. Composizione
    result = tmpl_rgb.copy()
    for c in range(3):
        # Moltiplichiamo i pixel della cover per le ombre del mockup
        result[y1:y1+th, x1:x1+tw, c] = cover_res[:, :, c] * shadow_map
        
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- LOGICA STREAMLIT (Semplificata e Robusta) ---
st.title("📖 Precision Mockup Compositor")

# Caricamento Templates
@st.cache_data
def load_templates():
    base = "templates"
    lib = {}
    if os.path.exists(base):
        for f in os.listdir(base):
            if f.lower().endswith(('.jpg', '.png')):
                lib[f] = Image.open(os.path.join(base, f))
    return lib

templates = load_templates()

if not templates:
    st.error("⚠️ Nessun template trovato nella cartella /templates")
else:
    col1, col2 = st.columns([1, 2])
    with col1:
        t_nome = st.selectbox("Seleziona Template:", list(templates.keys()))
        disegni = st.file_uploader("Carica le tue copertine:", accept_multiple_files=True)
    
    if st.button("🚀 GENERA MOCKUPS") and disegni:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a") as zip_file:
            bar = st.progress(0)
            for idx, d_file in enumerate(disegni):
                d_img = Image.open(d_file)
                res = composite_precision(templates[t_nome], d_img, t_nome)
                
                if res:
                    buf = io.BytesIO()
                    res.save(buf, format='JPEG', quality=95)
                    zip_file.writestr(f"Mockup_{d_file.name}", buf.getvalue())
                bar.progress((idx + 1) / len(disegni))
        
        st.success("✅ Generati con successo!")
        st.download_button("📥 Scarica ZIP", zip_buf.getvalue(), "mockups.zip")

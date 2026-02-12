import streamlit as st
import numpy as np
from PIL import Image
import os
import io
import zipfile

# --- 1. CONFIGURAZIONE E COORDINATE PRECISE ---
st.set_page_config(page_title="PhotoBook Production Pro", layout="wide")

# Inserisci qui le coordinate che hai trovato con il calibratore.
# Se le coordinate non sono perfette, basta cambiare questi numeri.
TEMPLATE_MAPS = {
    "base_verticale_temi_app.jpg": (35.1, 10.4, 29.8, 79.2),
    "base_orizzontale_temi_app.jpg": (19.4, 9.4, 61.2, 81.2),
    "base_orizzontale_temi_app3.jpg": (19.4, 9.4, 61.2, 81.2),
    "base_quadrata_temi_app.jpg": (28.2, 10.4, 43.6, 77.4),
    "base_bottom_app.jpg": (22.8, 4.4, 54.8, 89.6),
}

# --- 2. MOTORE DI COMPOSIZIONE ---
def composite_engine(tmpl_pil, cover_pil, filename):
    """Applica la copertina al template usando il mapping e le ombre."""
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    
    if filename not in TEMPLATE_MAPS:
        return None # Salta se il file non è mappato

    px, py, pw, ph = TEMPLATE_MAPS[filename]
    x1, y1 = int((px * w) / 100), int((py * h) / 100)
    tw, th = int((pw * w) / 100), int((ph * h) / 100)
    
    # Resize della cover
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # Shadow Map (Effetto Multiply) per il realismo della rilegatura
    book_shadows = tmpl_gray[y1:y1+th, x1:x1+tw]
    shadow_map = np.clip(book_shadows / 255.0, 0, 1.0)
    
    result = tmpl_rgb.copy()
    for c in range(3):
        # Fusione: Cover * Ombre originali
        result[y1:y1+th, x1:x1+tw, c] = cover_res[:, :, c] * shadow_map
        
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- 3. CARICAMENTO LIBRERIA TEMPLATE ---
@st.cache_data
def load_template_library():
    base_path = "templates" # Assicurati che la cartella esista
    lib = {}
    if os.path.exists(base_path):
        for f in os.listdir(base_path):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                lib[f] = Image.open(os.path.join(base_path, f))
    return lib

templates = load_template_library()

# --- 4. INTERFACCIA UTENTE ---
st.title("📖 PhotoBook Production System")

if not templates:
    st.error("❌ Cartella '/templates' non trovata o vuota. Carica i template lì dentro.")
else:
    with st.sidebar:
        st.header("Impostazioni")
        t_selezionato = st.selectbox("Scegli il Template:", list(templates.keys()))
        st.divider()
        st.info("Questo script usa coordinate fisse per una precisione millimetrica.")

    st.subheader("1. Carica i tuoi Design")
    disegni = st.file_uploader("Trascina qui i file delle copertine (JPG/PNG):", accept_multiple_files=True)

    if disegni:
        st.subheader(f"2. Elaborazione ({len(disegni)} file)")
        
        if st.button("🚀 GENERA E SCARICA TUTTO"):
            zip_buf = io.BytesIO()
            
            with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED) as zip_file:
                progress_bar = st.progress(0)
                
                for idx, d_file in enumerate(disegni):
                    d_img = Image.open(d_file)
                    # Applichiamo il motore di composizione
                    mockup_finale = composite_engine(templates[t_selezionato], d_img, t_selezionato)
                    
                    if mockup_finale:
                        # Salvataggio in memoria
                        img_byte_arr = io.BytesIO()
                        mockup_finale.save(img_byte_arr, format='JPEG', quality=95)
                        
                        # Aggiunta allo ZIP
                        nome_file = f"{os.path.splitext(d_file.name)[0]}_MOCKUP.jpg"
                        zip_file.writestr(nome_file, img_byte_arr.getvalue())
                    
                    progress_bar.progress((idx + 1) / len(disegni))
            
            st.success("✅ Generazione completata!")
            st.download_button(
                label="📥 SCARICA ZIP",
                data=zip_buf.getvalue(),
                file_name=f"Mockups_{t_selezionato}.zip",
                mime="application/zip"
            )

    # --- ANTEPRIMA RAPIDA ---
    if disegni and templates:
        st.divider()
        st.subheader("Anteprima dell'ultimo file")
        test_res = composite_engine(templates[t_selezionato], Image.open(disegni[-1]), t_selezionato)
        if test_res:
            st.image(test_res, use_column_width=True)

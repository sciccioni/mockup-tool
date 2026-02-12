import streamlit as st
import numpy as np
from PIL import Image
import io

# --- DIZIONARIO COORDINATE (Queste le salverai una volta calibrate) ---
TEMPLATE_MAPS = {
    "base_verticale_temi_app.jpg": (35.1, 10.4, 29.8, 79.2),
    "base_orizzontale_temi_app.jpg": (19.4, 9.4, 61.2, 81.2),
    "base_orizzontale_temi_app3.jpg": (19.4, 9.4, 61.2, 81.2),
    "base_quadrata_temi_app.jpg": (28.2, 10.4, 43.6, 77.4),
    "base_bottom_app.jpg": (22.8, 4.4, 54.8, 89.6),
}

def apply_mockup(tmpl_pil, cover_pil, x_pct, y_pct, w_pct, h_pct):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    
    # Conversione percentuali -> pixel
    x1, y1 = int((x_pct * w) / 100), int((y_pct * h) / 100)
    tw, th = int((w_pct * w) / 100), int((h_pct * h) / 100)
    
    # Resize cover
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # Shadow Map (Multiply) - Prende le ombre originali del libro
    book_shadows = tmpl_gray[y1:y1+th, x1:x1+tw]
    shadow_map = np.clip(book_shadows / 255.0, 0, 1.0)
    
    result = tmpl_rgb.copy()
    for c in range(3):
        result[y1:y1+th, x1:x1+tw, c] = cover_res[:, :, c] * shadow_map
        
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

st.title("🛠️ Calibratore Mockup Ultra-Preciso")

st.sidebar.header("⚙️ Regolazione Fine")

# Seleziona il template per vedere i valori salvati o modificarli
t_nome = st.sidebar.selectbox("Template da calibrare", list(TEMPLATE_MAPS.keys()))
default_vals = TEMPLATE_MAPS.get(t_nome, (0, 0, 100, 100))

# SLIDERS PER TROVARE I PUNTI ESATTI
sc_x = st.sidebar.slider("X (Inizio Orizzontale %)", 0.0, 100.0, default_vals[0], 0.1)
sc_y = st.sidebar.slider("Y (Inizio Verticale %)", 0.0, 100.0, default_vals[1], 0.1)
sc_w = st.sidebar.slider("Larghezza (%)", 0.0, 100.0, default_vals[2], 0.1)
sc_h = st.sidebar.slider("Altezza (%)", 0.0, 100.0, default_vals[3], 0.1)

st.info(f"📍 Coordinate attuali da copiare nel codice: **({sc_x}, {sc_y}, {sc_w}, {sc_h})**")

# Caricamento file per test
col_t, col_c = st.columns(2)
with col_t:
    up_tmpl = st.file_uploader("Carica il Template JPG", type=['jpg', 'jpeg'])
with col_c:
    up_cover = st.file_uploader("Carica una Copertina di test", type=['jpg', 'png'])

if up_tmpl and up_cover:
    img_t = Image.open(up_tmpl)
    img_c = Image.open(up_cover)
    
    # Anteprima in tempo reale
    result_img = apply_mockup(img_t, img_c, sc_x, sc_y, sc_w, sc_h)
    st.image(result_img, caption="Anteprima Calibrazione", use_column_width=True)
    
    # Mostra anche il template originale per riferimento
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.image(img_t, caption="Template Originale", use_column_width=True)
    with col2:
        st.image(img_c, caption="Cover di Test", use_column_width=True)

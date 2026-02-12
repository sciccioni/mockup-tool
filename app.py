import streamlit as st
import numpy as np
from PIL import Image, ImageDraw

st.set_page_config(layout="wide", page_title="Calibratore Pro V2.5")

# --- MOTORE DI RENDERING ---
def create_clean_preview(tmpl_img, cover_img, coords, show_border):
    preview = tmpl_img.convert('RGB').copy()
    draw = ImageDraw.Draw(preview)
    w_f, h_f = preview.size
    
    px, py, pw, ph = coords
    x1, y1 = int((px * w_f) / 100), int((py * h_f) / 100)
    tw, th = int((pw * w_f) / 100), int((ph * h_f) / 100)
    x2, y2 = x1 + tw, y1 + th

    if cover_img:
        # Incolliamo la cover con resize di alta qualità
        cover_res = cover_img.convert('RGB').resize((tw, th), Image.LANCZOS)
        preview.paste(cover_res, (x1, y1))
    
    # Il bordo rosso compare SOLO se lo attivi tu
    if show_border:
        draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
        
    return preview

# --- INTERFACCIA ---
st.title("🎯 Calibrazione Millimetrica Senza Distrazioni")

# Setup dello stato per non perdere i dati
if 'coords' not in st.session_state:
    st.session_state.coords = [15.0, 15.0, 70.0, 70.0]

col_ctrl, col_view = st.columns([1, 3]) # Colonna preview più grande

with col_ctrl:
    st.subheader("1. File")
    up_t = st.file_uploader("Template", type=['jpg', 'png'], key="t")
    up_c = st.file_uploader("Cover di Test", type=['jpg', 'png'], key="c")
    
    st.divider()
    st.subheader("2. Regolazione")
    
    # Interruttore per il bordo
    border_on = st.checkbox("Mostra rettangolo guida", value=False)
    
    # Sliders per il posizionamento
    st.session_state.coords[0] = st.slider("X (Orizzontale)", 0.0, 100.0, st.session_state.coords[0], 0.1)
    st.session_state.coords[1] = st.slider("Y (Verticale)", 0.0, 100.0, st.session_state.coords[1], 0.1)
    st.session_state.coords[2] = st.slider("Larghezza (W)", 0.0, 100.0, st.session_state.coords[2], 0.1)
    st.session_state.coords[3] = st.slider("Altezza (H)", 0.0, 100.0, st.session_state.coords[3], 0.1)
    
    st.divider()
    st.subheader("3. Codice")
    if up_t:
        st.code(f"'{up_t.name}': {st.session_state.coords},")

with col_view:
    if up_t:
        img_t = Image.open(up_t)
        img_c = Image.open(up_c) if up_c else None
        
        # Genera l'immagine finale pulita
        res = create_clean_preview(img_t, img_c, st.session_state.coords, border_on)
        st.image(res, use_container_width=True) # Dimensione massima possibile
    else:
        st.info("Carica un template per iniziare la calibrazione.")

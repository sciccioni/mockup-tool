import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw

st.set_page_config(layout="wide", page_title="Calibratore Pro V3.0")

def apply_blending(tmpl_pil, cover_pil, coords):
    """Applica il blending reale (Multiply) per la calibrazione."""
    tmpl_rgb = tmpl_pil.convert('RGB')
    w_f, h_f = tmpl_rgb.size
    px, py, pw, ph = coords
    
    # Conversione percentuali -> pixel
    x1, y1 = int((px * w_f) / 100), int((py * h_f) / 100)
    tw, th = int((pw * w_f) / 100), int((ph * h_f) / 100)
    
    # Resize cover
    cover_res = cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)
    cover_arr = np.array(cover_res).astype(np.float64)
    
    # Shadow Map (Texture del libro)
    crop_gray = np.array(tmpl_pil.convert('L').crop((x1, y1, x1+tw, y1+th))).astype(np.float64)
    shadow_map = np.expand_dims(np.clip(crop_gray / 255.0, 0.0, 1.0), axis=2)
    
    # Moltiplicazione (Blending)
    blended = (cover_arr * shadow_map).astype(np.uint8)
    
    # Ricostruzione finale
    final_img = tmpl_rgb.copy()
    final_img.paste(Image.fromarray(blended), (x1, y1))
    return final_img

# --- INTERFACCIA ---
st.title("🎯 Calibrazione con Blending & Proporzioni Bloccate")

if 'coords' not in st.session_state:
    st.session_state.coords = [15.0, 15.0, 70.0, 70.0]

col_ctrl, col_view = st.columns([1, 2])

with col_ctrl:
    st.subheader("1. Carica File")
    up_t = st.file_uploader("Template JPG", type=['jpg', 'png'])
    up_c = st.file_uploader("Cover di Prova", type=['jpg', 'png'])
    
    if up_t and up_c:
        img_t = Image.open(up_t)
        img_c = Image.open(up_c)
        w_c, h_c = img_c.size
        aspect_ratio = h_c / w_c
        
        st.divider()
        st.subheader("2. Controllo Dimensioni")
        
        lock_aspect = st.checkbox("Blocca Proporzioni (Anti-Distorsione)", value=True)
        
        # Se bloccato, l'altezza si calcola in base alla larghezza
        st.session_state.coords[2] = st.slider("Larghezza (%)", 0.0, 100.0, st.session_state.coords[2], 0.1)
        
        if lock_aspect:
            # Calcolo automatico altezza per non distorcere
            # Tenendo conto che le percentuali dipendono dai pixel del template
            w_tmpl, h_tmpl = img_t.size
            h_perc = (st.session_state.coords[2] * w_tmpl * aspect_ratio) / h_tmpl
            st.session_state.coords[3] = round(h_perc, 1)
            st.info(f"Altezza calcolata: {st.session_state.coords[3]}% (Ratio: {round(aspect_ratio, 2)})")
        else:
            st.session_state.coords[3] = st.slider("Altezza (%)", 0.0, 100.0, st.session_state.coords[3], 0.1)

        st.divider()
        st.subheader("3. Posizionamento")
        st.session_state.coords[0] = st.slider("Sposta X (%)", 0.0, 100.0, st.session_state.coords[0], 0.1)
        st.session_state.coords[1] = st.slider("Sposta Y (%)", 0.0, 100.0, st.session_state.coords[1], 0.1)
        
        st.divider()
        st.subheader("4. Risultato")
        st.code(f"'{up_t.name}': {st.session_state.coords},")

with col_view:
    if up_t and up_c:
        res = apply_blending(img_t, img_c, st.session_state.coords)
        st.image(res, caption="Anteprima REALE con Blending", use_container_width=True)
    else:
        st.info("Carica sia il template che la cover per vedere il blending.")

import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw

st.set_page_config(layout="wide", page_title="Calibratore Precisione V3.1")

def apply_blending(tmpl_pil, cover_pil, coords):
    """Applica il blending reale (Multiply) per la calibrazione."""
    tmpl_rgb = tmpl_pil.convert('RGB')
    w_f, h_f = tmpl_rgb.size
    px, py, pw, ph = coords
    
    # Conversione percentuali -> pixel
    x1, y1 = int((px * w_f) / 100), int((py * h_f) / 100)
    tw, th = int((pw * w_f) / 100), int((ph * h_f) / 100)
    
    # Protezione per dimensioni zero o negative
    tw, th = max(1, tw), max(1, th)
    
    # Resize cover
    cover_res = cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)
    cover_arr = np.array(cover_res).astype(np.float64)
    
    # Shadow Map (Texture del libro)
    crop_area = tmpl_pil.convert('L').crop((x1, y1, x1+tw, y1+th))
    crop_gray = np.array(crop_area).astype(np.float64)
    shadow_map = np.expand_dims(np.clip(crop_gray / 255.0, 0.0, 1.0), axis=2)
    
    # Moltiplicazione (Blending)
    blended = (cover_arr * shadow_map).astype(np.uint8)
    
    # Ricostruzione finale
    final_img = tmpl_rgb.copy()
    final_img.paste(Image.fromarray(blended), (x1, y1))
    return final_img

# --- INTERFACCIA ---
st.title("🎯 Calibrazione Millimetrica (+ / -)")

if 'coords' not in st.session_state:
    # [X, Y, W, H]
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
        st.subheader("2. Regolazione Fine")
        
        lock_aspect = st.checkbox("Blocca Proporzioni (Anti-Storpiamento)", value=True)
        
        # Uso di number_input per avere i tasti + e -
        # Passo (step) impostato a 0.1 per la massima precisione
        
        st.write("**Dimensioni**")
        c_w, c_h = st.columns(2)
        with c_w:
            st.session_state.coords[2] = st.number_input("Larghezza (W %)", value=st.session_state.coords[2], step=0.1, format="%.1f")
        
        if lock_aspect:
            w_tmpl, h_tmpl = img_t.size
            h_perc = (st.session_state.coords[2] * w_tmpl * aspect_ratio) / h_tmpl
            st.session_state.coords[3] = round(h_perc, 1)
            with c_h:
                st.write(f"Altezza (H %)\n\n**{st.session_state.coords[3]}** (Auto)")
        else:
            with c_h:
                st.session_state.coords[3] = st.number_input("Altezza (H %)", value=st.session_state.coords[3], step=0.1, format="%.1f")

        st.write("**Posizionamento**")
        c_x, c_y = st.columns(2)
        with c_x:
            st.session_state.coords[0] = st.number_input("Sposta X (%)", value=st.session_state.coords[0], step=0.1, format="%.1f")
        with c_y:
            st.session_state.coords[1] = st.number_input("Sposta Y (%)", value=st.session_state.coords[1], step=0.1, format="%.1f")
        
        st.divider()
        st.subheader("3. Codice da Copiare")
        st.code(f"'{up_t.name}': {st.session_state.coords},", language="python")

with col_view:
    if up_t and up_c:
        res = apply_blending(img_t, img_c, st.session_state.coords)
        st.image(res, caption="Anteprima REALE con Blending e Pixel-Precision", use_container_width=True)
    else:
        st.info("Carica template e cover per attivare i controlli.")

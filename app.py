import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import os
import io
import zipfile

# --- 1. SETUP E COORDINATE SALVATE ---
st.set_page_config(page_title="PhotoBook Master V6.1", layout="wide")

if 'coords' not in st.session_state:
    st.session_state.coords = {
        "base_copertina_verticale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_copertina_orizzontale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_verticale_temi_app.jpg": [34.6, 9.2, 30.2, 80.3],
        "base_bottom_app.jpg": [21.9, 4.9, 56.5, 91.3],
        "base_orizzontale_temi_app.jpg": [18.9, 9.4, 61.8, 83.0],
        "base_orizzontale_temi_app3.jpg": [18.7, 9.4, 62.2, 82.6],
        "base_quadrata_temi_app.jpg": [27.8, 10.8, 44.5, 79.0],
        "30x30-crea la tua grafica.jpg": [5.0, 5.0, 90.0, 90.0],
    }

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- 2. MOTORE DI RENDERING (ANTI-CRASH) ---
def get_feathered_mask(size, blur_radius):
    mask = Image.new("L", size, 255)
    if blur_radius > 0:
        draw = ImageDraw.Draw(mask)
        offset = int(blur_radius / 2) + 1
        draw.rectangle([0, 0, size[0], size[1]], outline=0, width=offset)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    return mask

def process_mockup(tmpl_pil, cover_pil, t_name, blur_rad):
    # Convertiamo tutto in RGB/L e array
    tmpl_img = tmpl_pil.convert('RGB')
    tmpl_gray = tmpl_pil.convert('L')
    w_full, h_full = tmpl_img.size
    
    # Recupero coordinate
    if t_name not in st.session_state.coords:
        st.session_state.coords[t_name] = [10.0, 10.0, 80.0, 80.0]
    
    px, py, pw, ph = st.session_state.coords[t_name]
    
    # Calcolo pixel esatti
    x1 = int((px * w_full) / 100)
    y1 = int((py * h_full) / 100)
    tw = int((pw * w_full) / 100)
    th = int((ph * h_full) / 100)
    
    # Protezione: non uscire dai bordi del template
    tw = min(tw, w_full - x1)
    th = min(th, h_full - y1)
    if tw <= 0 or th <= 0: return None

    # Ritaglio e preparazione shadow map
    tmpl_crop_gray = np.array(tmpl_gray.crop((x1, y1, x1 + tw, y1 + th))).astype(np.float64)
    shadow_map = np.clip(tmpl_crop_gray / 255.0, 0.0, 1.0)
    shadow_map = np.expand_dims(shadow_map, axis=2) # Shape: (th, tw, 1)

    # Resize cover ESATTO al ritaglio effettuato
    cover_res = cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)
    cover_arr = np.array(cover_res).astype(np.float64) # Shape: (th, tw, 3)

    # Maschera sfocatura
    f_mask = get_feathered_mask((tw, th), blur_rad)
    alpha = np.array(f_mask).astype(np.float64) / 255.0
    alpha = np.expand_dims(alpha, axis=2)

    # Blending: moltiplichiamo la cover per le ombre (Multiply)
    cover_final = cover_arr * shadow_map
    
    # Composizione con sfondo originale
    tmpl_crop_rgb = np.array(tmpl_img.crop((x1, y1, x1 + tw, y1 + th))).astype(np.float64)
    blended = (cover_final * alpha) + (tmpl_crop_rgb * (1 - alpha))
    
    # Ricostruzione immagine finale
    result_np = np.array(tmpl_img).copy()
    result_np[y1:y1+th, x1:x1+tw] = np.clip(blended, 0, 255).astype(np.uint8)
    
    return Image.fromarray(result_np)

# --- 3. SMISTAMENTO ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["verticale", "bottom", "15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["orizzontale", "20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["quadrata", "20x20", "30x30"]): return "Quadrati"
    return "Altro"

@st.cache_data(show_spinner=False)
def load_library():
    path = "templates"
    if not os.path.exists(path): os.makedirs(path)
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}, "Altro": {}, "Tutti": {}}
    for f in os.listdir(path):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            img = Image.open(os.path.join(path, f))
            lib["Tutti"][f] = img
            cat = get_manual_cat(f)
            lib[cat][f] = img
    return lib

libreria = load_library()

# --- 4. INTERFACCIA ---
st.title("📖 PhotoBook Master V6.1")

tab_prod, tab_sett = st.tabs(["🚀 PRODUZIONE", "⚙️ IMPOSTAZIONI"])

with tab_prod:
    c_ctrl, c_up = st.columns([1, 2])
    with c_ctrl:
        categoria = st.radio("Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
        sfoca = st.slider("Sfocatura bordi:", 0.0, 15.0, 5.0, 0.5)
        if st.button("🗑️ RESET"):
            st.session_state.uploader_key += 1
            st.rerun()
    with c_up:
        disegni = st.file_uploader("Carica design:", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

    if disegni and libreria[categoria]:
        if st.button("🚀 GENERA ZIP"):
            zip_io = io.BytesIO()
            with zipfile.ZipFile(zip_io, "a") as zf:
                for d_file in disegni:
                    d_img = Image.open(d_file)
                    d_fn = os.path.splitext(d_file.name)[0]
                    for t_name, t_img in libreria[categoria].items():
                        res = process_mockup(t_img, d_img, t_name, sfoca)
                        if res:
                            buf = io.BytesIO()
                            res.save(buf, format='JPEG', quality=95)
                            zf.writestr(f"{d_fn}/{t_name}.jpg", buf.getvalue())
            st.download_button("📥 SCARICA ZIP", zip_io.getvalue(), "Mockups.zip")
        
        t_pre = list(libreria[categoria].keys())[0]
        st.image(process_mockup(libreria[categoria][t_pre], Image.open(disegni[-1]), t_pre, sfoca), use_column_width=True)

with tab_sett:
    st.subheader("⚙️ Calibrazione Template")
    if libreria["Tutti"]:
        t_mod = st.selectbox("Seleziona template:", list(libreria["Tutti"].keys()))
        if t_mod not in st.session_state.coords:
            st.session_state.coords[t_mod] = [10.0, 10.0, 80.0, 80.0]
            
        c_in, c_pre = st.columns([1, 2])
        with c_in:
            st.session_state.coords[t_mod][0] = st.number_input("X %", value=st.session_state.coords[t_mod][0], step=0.1)
            st.session_state.coords[t_mod][1] = st.number_input("Y %", value=st.session_state.coords[t_mod][1], step=0.1)
            st.session_state.coords[t_mod][2] = st.number_input("W %", value=st.session_state.coords[t_mod][2], step=0.1)
            st.session_state.coords[t_mod][3] = st.number_input("H %", value=st.session_state.coords[t_mod][3], step=0.1)
            t_cov_test = st.file_uploader("Cover test:", type=['jpg', 'png'])
            st.code(f"'{t_mod}': {st.session_state.coords[t_mod]},")
        with c_pre:
            if t_cov_test:
                st.image(process_mockup(libreria["Tutti"][t_mod], Image.open(t_cov_test), t_mod, 5.0), use_column_width=True)

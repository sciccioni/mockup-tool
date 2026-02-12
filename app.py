import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import os
import io
import zipfile

# --- 1. SETUP E COORDINATE ---
st.set_page_config(page_title="PhotoBook Master V7.5", layout="wide")

if 'coords' not in st.session_state:
    st.session_state.coords = {
        "base_copertina_verticale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_copertina_orizzontale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_verticale_temi_app.jpg": [34.6, 9.2, 30.2, 80.3],
        "base_bottom_app.jpg": [21.9, 4.9, 56.5, 91.3],
        "base_orizzontale_temi_app.jpg": [18.9, 9.4, 61.8, 83.0],
        "base_orizzontale_temi_app3.jpg": [18.7, 9.4, 62.2, 82.6],
        "base_quadrata_temi_app.jpg": [27.8, 10.8, 44.5, 79.0],
        "30x30-crea la tua grafica.jpg": [15.0, 15.0, 70.0, 70.0],
    }

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- 2. MOTORE DI RENDERING (FULL BLENDING) ---
def get_feathered_mask(size, blur_radius):
    mask = Image.new("L", size, 255)
    if blur_radius > 0:
        draw = ImageDraw.Draw(mask)
        offset = int(blur_radius / 2) + 1
        draw.rectangle([0, 0, size[0], size[1]], outline=0, width=offset)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    return mask

def process_mockup(tmpl_pil, cover_pil, t_name, blur_rad):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    w_f, h_f = tmpl_pil.size
    
    if t_name not in st.session_state.coords:
        st.session_state.coords[t_name] = [0.0, 0.0, 100.0, 100.0]

    px, py, pw, ph = st.session_state.coords[t_name]
    x1, y1 = int((px * w_f) / 100), int((py * h_f) / 100)
    tw, th = int((pw * w_f) / 100), int((ph * h_f) / 100)
    
    tw, th = max(1, min(tw, w_f - x1)), max(1, min(th, h_f - y1))
    
    crop_gray = np.array(tmpl_pil.convert('L').crop((x1, y1, x1+tw, y1+th))).astype(np.float64)
    shadow_map = np.expand_dims(np.clip(crop_gray / 255.0, 0.0, 1.0), axis=2)
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    f_mask = get_feathered_mask((tw, th), blur_rad)
    alpha = np.expand_dims(np.array(f_mask).astype(np.float64) / 255.0, axis=2)

    orig_area = np.array(tmpl_pil.convert('RGB').crop((x1, y1, x1+tw, y1+th))).astype(np.float64)
    cover_shadowed = cover_res * shadow_map
    blended = (cover_shadowed * alpha) + (orig_area * (1 - alpha))
    
    result = np.array(tmpl_pil.convert('RGB')).copy()
    result[y1:y1+th, x1:x1+tw] = np.clip(blended, 0, 255).astype(np.uint8)
    return Image.fromarray(result)

# --- 3. SMISTAMENTO TEMPLATE ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["verticale", "bottom", "15x22", "20x30"]):
        return "Verticali"
    if any(x in fn for x in ["orizzontale", "20x15", "27x20", "32x24", "40x30"]):
        return "Orizzontali"
    if any(x in fn for x in ["quadrata", "20x20", "30x30"]):
        return "Quadrati"
    return "Altro"

@st.cache_data(show_spinner=False)
def load_library():
    path = "templates"
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}, "Tutti": {}}
    if os.path.exists(path):
        for f in os.listdir(path):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                img = Image.open(os.path.join(path, f))
                lib["Tutti"][f] = img
                cat = get_manual_cat(f)
                if cat in lib: lib[cat][f] = img
    return lib

libreria = load_library()

# --- 4. INTERFACCIA ---
tab_prod, tab_sett = st.tabs(["🚀 PRODUZIONE BATCH", "⚙️ IMPOSTAZIONI"])

with tab_prod:
    col_l, col_r = st.columns([1, 2])
    with col_l:
        formato = st.radio("Scegli Categoria:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
        sfocatura = st.slider("Sfocatura Bordi (px):", 0.0, 15.0, 5.0, 0.5)
        if st.button("🗑️ RESET"):
            st.session_state.uploader_key += 1
            st.rerun()
    with col_r:
        disegni = st.file_uploader("Carica copertine:", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

    if disegni and libreria[formato]:
        if st.button("🚀 GENERA ZIP"):
            z_io = io.BytesIO()
            with zipfile.ZipFile(zip_io, "a") as zf:
                for d in disegni:
                    d_img = Image.open(d)
                    for t_n, t_i in libreria[formato].items():
                        res = process_mockup(t_i, d_img, t_n, sfocatura)
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zf.writestr(f"{os.path.splitext(d.name)[0]}/{t_n}.jpg", buf.getvalue())
            st.download_button("📥 SCARICA ZIP", z_io.getvalue(), "Mockups.zip")
        
        st.divider()
        st.subheader(f"Anteprime di TUTTI i template {formato}")
        
        # --- GRIGLIA ANTEPRIME ---
        targets = libreria[formato]
        grid = st.columns(2) # 2 colonne per vedere bene i dettagli
        for idx, (name, img) in enumerate(targets.items()):
            with grid[idx % 2]:
                st.caption(f"File: {name}")
                st.image(process_mockup(img, Image.open(disegni[-1]), name, sfocatura), use_column_width=True)

with tab_sett:
    st.subheader("🛠️ Calibrazione")
    if libreria["Tutti"]:
        t_mod = st.selectbox("Seleziona template:", list(libreria["Tutti"].keys()))
        c_in, c_pre = st.columns([1, 2])
        with c_in:
            if t_mod not in st.session_state.coords:
                st.session_state.coords[t_mod] = [0.0, 0.0, 100.0, 100.0]
            st.session_state.coords[t_mod][0] = st.number_input("X %", value=st.session_state.coords[t_mod][0], step=0.1)
            st.session_state.coords[t_mod][1] = st.number_input("Y %", value=st.session_state.coords[t_mod][1], step=0.1)
            st.session_state.coords[t_mod][2] = st.number_input("W %", value=st.session_state.coords[t_mod][2], step=0.1)
            st.session_state.coords[t_mod][3] = st.number_input("H %", value=st.session_state.coords[t_mod][3], step=0.1)
            t_test = st.file_uploader("Immagine di test:", type=['jpg', 'png'], key="test_u")
            st.code(f"'{t_mod}': {st.session_state.coords[t_mod]},")
        with c_pre:
            if t_test:
                st.image(process_mockup(libreria["Tutti"][t_mod], Image.open(t_test), t_mod, 5.0), use_column_width=True)

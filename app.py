import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import os
import io
import zipfile

# --- 1. COORDINATE SALVATE ---
st.set_page_config(page_title="PhotoBook Master V6.2", layout="wide")

if 'coords' not in st.session_state:
    st.session_state.coords = {
        "base_copertina_verticale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_copertina_orizzontale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_verticale_temi_app.jpg": [34.6, 9.2, 30.2, 80.3],
        "base_bottom_app.jpg": [21.9, 4.9, 56.5, 91.3],
        "base_orizzontale_temi_app.jpg": [18.9, 9.4, 61.8, 83.0],
        "base_orizzontale_temi_app3.jpg": [18.7, 9.4, 62.2, 82.6],
        "base_quadrata_temi_app.jpg": [27.8, 10.8, 44.5, 79.0],
        # STIMA PER 30x30 (Regolala se non è perfetta, ma ora non crasha)
        "30x30-crea la tua grafica.jpg": [5.0, 5.0, 90.0, 90.0],
    }

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- 2. MOTORE DI RENDERING ---
def process_mockup(tmpl_pil, cover_pil, t_name, blur_rad):
    tmpl_img = tmpl_pil.convert('RGB')
    tmpl_gray = tmpl_pil.convert('L')
    w_f, h_f = tmpl_img.size
    
    if t_name not in st.session_state.coords:
        st.session_state.coords[t_name] = [10.0, 10.0, 80.0, 80.0]
    
    px, py, pw, ph = st.session_state.coords[t_name]
    
    # Calcolo pixel e clamp per evitare crash
    x1, y1 = int((px * w_f) / 100), int((py * h_f) / 100)
    tw, th = int((pw * w_f) / 100), int((ph * h_f) / 100)
    tw, th = min(tw, w_f - x1), min(th, h_f - y1)
    
    if tw <= 0 or th <= 0: return tmpl_img

    # Ombre (Shadow Map)
    crop_gray = np.array(tmpl_gray.crop((x1, y1, x1+tw, y1+th))).astype(np.float64)
    shadow_map = np.expand_dims(np.clip(crop_gray / 255.0, 0.0, 1.0), axis=2)

    # Cover e Maschera
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    mask = Image.new("L", (tw, th), 255)
    if blur_rad > 0:
        draw = ImageDraw.Draw(mask)
        draw.rectangle([0, 0, tw, th], outline=0, width=int(blur_rad/2)+1)
        mask = mask.filter(ImageFilter.GaussianBlur(blur_rad))
    alpha = np.expand_dims(np.array(mask).astype(np.float64) / 255.0, axis=2)

    # Blending
    crop_orig = np.array(tmpl_img.crop((x1, y1, x1+tw, y1+th))).astype(np.float64)
    blended = ((cover_res * shadow_map) * alpha) + (crop_orig * (1 - alpha))
    
    final_np = np.array(tmpl_img).copy()
    final_np[y1:y1+th, x1:x1+tw] = np.clip(blended, 0, 255).astype(np.uint8)
    return Image.fromarray(final_np)

# --- 3. LOGICA CATEGORIE ---
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
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}, "Tutti": {}}
    for f in os.listdir(path):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            img = Image.open(os.path.join(path, f))
            lib["Tutti"][f] = img
            cat = get_manual_cat(f)
            if cat in lib: lib[cat][f] = img
    return lib

libreria = load_library()

# --- 4. UI ---
st.title("📖 PhotoBook Master V6.2")

t_prod, t_sett = st.tabs(["🚀 PRODUZIONE", "⚙️ IMPOSTAZIONI"])

with t_prod:
    col_l, col_r = st.columns([1, 2])
    with col_l:
        cat = st.radio("Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
        blur = st.slider("Sfocatura:", 0.0, 10.0, 5.0, 0.5)
        if st.button("🗑️ RESET"):
            st.session_state.uploader_key += 1
            st.rerun()
    with col_r:
        disegni = st.file_uploader("Carica design:", accept_multiple_files=True, key=f"u_{st.session_state.uploader_key}")

    if disegni and libreria[cat]:
        if st.button("🚀 ZIP"):
            z_io = io.BytesIO()
            with zipfile.ZipFile(z_io, "a") as zf:
                for d in disegni:
                    d_img = Image.open(d)
                    for t_n, t_i in libreria[cat].items():
                        res = process_mockup(t_i, d_img, t_n, blur)
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zf.writestr(f"{os.path.splitext(d.name)[0]}/{t_n}.jpg", buf.getvalue())
            st.download_button("📥 SCARICA", z_io.getvalue(), "Mockups.zip")
        st.image(process_mockup(list(libreria[cat].values())[0], Image.open(disegni[-1]), list(libreria[cat].keys())[0], blur))

with t_sett:
    if libreria["Tutti"]:
        t_sel = st.selectbox("Template:", list(libreria["Tutti"].keys()))
        c_i, c_p = st.columns([1, 2])
        with c_i:
            # COORDINATE EDITABILI
            st.session_state.coords[t_sel][0] = st.number_input("X %", value=st.session_state.coords[t_sel][0], step=0.1)
            st.session_state.coords[t_sel][1] = st.number_input("Y %", value=st.session_state.coords[t_sel][1], step=0.1)
            st.session_state.coords[t_sel][2] = st.number_input("W %", value=st.session_state.coords[t_sel][2], step=0.1)
            st.session_state.coords[t_sel][3] = st.number_input("H %", value=st.session_state.coords[t_sel][3], step=0.1)
            t_test = st.file_uploader("Test Img:", type=['jpg', 'png'])
            st.code(f"'{t_sel}': {st.session_state.coords[t_sel]},")
        with c_p:
            if t_test:
                st.image(process_mockup(libreria["Tutti"][t_sel], Image.open(t_test), t_sel, 5.0))

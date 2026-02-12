import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import os
import io
import zipfile

# --- 1. SETUP E COORDINATE ---
st.set_page_config(page_title="PhotoBook Master V6.0", layout="wide")

if 'coords' not in st.session_state:
    st.session_state.coords = {
        # Template Piatti (Pieno formato)
        "base_copertina_verticale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_copertina_orizzontale.jpg": [0.0, 0.0, 100.0, 100.0],
        # Template con libro fotografato (Esempi già calibrati)
        "base_verticale_temi_app.jpg": [34.6, 9.2, 30.2, 80.3],
        "base_bottom_app.jpg": [21.9, 4.9, 56.5, 91.3],
        "base_orizzontale_temi_app.jpg": [18.9, 9.4, 61.8, 83.0],
        "base_orizzontale_temi_app3.jpg": [18.7, 9.4, 62.2, 82.6],
        "base_quadrata_temi_app.jpg": [27.8, 10.8, 44.5, 79.0],
        # 30x30: Lo facciamo partire piccolo (50%) per farti vedere i bordi
        "30x30-crea la tua grafica.jpg": [25.0, 25.0, 50.0, 50.0], 
    }

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- 2. MOTORE DI RENDERING ---
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
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    
    # Inizializzazione di emergenza
    if t_name not in st.session_state.coords:
        st.session_state.coords[t_name] = [20.0, 20.0, 60.0, 60.0]

    px, py, pw, ph = st.session_state.coords[t_name]
    x1, y1 = int((px * w) / 100), int((py * h) / 100)
    tw, th = int((pw * w) / 100), int((ph * h) / 100)
    
    # Protezione dimensioni
    tw, th = max(1, tw), max(1, th)
    
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # Shadow Map (Moltiplicazione per ombre e texture)
    shadow_map = np.clip(tmpl_gray[y1:y1+th, x1:x1+tw] / 255.0, 0.0, 1.0)
    shadow_map = np.expand_dims(shadow_map, axis=2)

    # Maschera per bordi morbidi
    f_mask = get_feathered_mask((tw, th), blur_rad)
    alpha = np.array(f_mask).astype(np.float64) / 255.0
    alpha = np.expand_dims(alpha, axis=2)

    # Blending finale
    orig_area = tmpl_rgb[y1:y1+th, x1:x1+tw]
    cover_final = cover_res * shadow_map
    blended = (cover_final * alpha) + (orig_area * (1 - alpha))
    
    result = tmpl_rgb.copy()
    result[y1:y1+th, x1:x1+tw] = blended
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

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
tab_prod, tab_sett = st.tabs(["🚀 PRODUZIONE", "⚙️ IMPOSTAZIONI"])

with tab_prod:
    st.subheader("Batch Mockup")
    formato = st.radio("Categoria:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
    disegni = st.file_uploader("Carica design:", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

    if disegni and libreria[formato]:
        if st.button("🚀 GENERA ZIP"):
            zip_io = io.BytesIO()
            with zipfile.ZipFile(zip_io, "a") as zf:
                for d_file in disegni:
                    d_img = Image.open(d_file)
                    d_fn = os.path.splitext(d_file.name)[0]
                    for t_name, t_img in libreria[formato].items():
                        res = process_mockup(t_img, d_img, t_name, 5.0)
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zf.writestr(f"{d_fn}/{t_name}.jpg", buf.getvalue())
            st.download_button("📥 SCARICA ZIP", zip_io.getvalue(), "Mockups.zip")

with tab_sett:
    st.subheader("🛠️ Calibrazione Millimetrica")
    if libreria["Tutti"]:
        t_mod = st.selectbox("Seleziona template:", list(libreria["Tutti"].keys()))
        
        # Inizializza se nuovo
        if t_mod not in st.session_state.coords:
            st.session_state.coords[t_mod] = [20.0, 20.0, 60.0, 60.0]
            
        col_in, col_pre = st.columns([1, 2])
        
        with col_in:
            st.write("**Regola la dimensione:**")
            st.session_state.coords[t_mod][0] = st.slider("Posizione X %", 0.0, 100.0, st.session_state.coords[t_mod][0])
            st.session_state.coords[t_mod][1] = st.slider("Posizione Y %", 0.0, 100.0, st.session_state.coords[t_mod][1])
            st.session_state.coords[t_mod][2] = st.slider("Larghezza (W) %", 0.0, 100.0, st.session_state.coords[t_mod][2])
            st.session_state.coords[t_mod][3] = st.slider("Altezza (H) %", 0.0, 100.0, st.session_state.coords[t_mod][3])
            
            t_cov_test = st.file_uploader("Carica cover per test:", type=['jpg', 'png'])
            st.code(f"'{t_mod}': {st.session_state.coords[t_mod]},")

        with col_pre:
            if t_cov_test:
                # Mostriamo l'anteprima con i bordi del libro visibili
                st.image(process_mockup(libreria["Tutti"][t_mod], Image.open(t_cov_test), t_mod, 5.0), use_column_width=True)
            else:
                st.warning("Carica un'immagine nel riquadro a sinistra per iniziare a centrare.")

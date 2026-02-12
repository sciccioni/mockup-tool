import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import os
import io
import zipfile

# --- 1. SETUP E SMISTAMENTO RIGIDO ---
st.set_page_config(page_title="PhotoBook Master V7.0", layout="wide")

def get_manual_cat(filename):
    fn = filename.lower()
    # Ordine di priorità: Orizzontali (32x24, 40x30 sono qui), poi Verticali, poi Quadrati
    if any(x in fn for x in ["32x24", "40x30", "orizzontale", "20x15", "27x20"]):
        return "Orizzontali"
    if any(x in fn for x in ["20x30", "verticale", "bottom", "15x22"]):
        return "Verticali"
    if any(x in fn for x in ["30x30", "quadrata", "20x20"]):
        return "Quadrati"
    return "Altro"

# Inizializzazione coordinate calibrate (se vuoi resettare, cancella la cache del browser)
if 'coords' not in st.session_state:
    st.session_state.coords = {
        "base_copertina_verticale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_copertina_orizzontale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_verticale_temi_app.jpg": [34.6, 9.2, 30.2, 80.3],
        "base_bottom_app.jpg": [21.9, 4.9, 56.5, 91.3],
        "base_orizzontale_temi_app.jpg": [18.9, 9.4, 61.8, 83.0],
        "base_orizzontale_temi_app3.jpg": [18.7, 9.4, 62.2, 82.6],
        "base_quadrata_temi_app.jpg": [27.8, 10.8, 44.5, 79.0],
        # Per il 30x30 partiamo con margini larghi (se è troppo grande, diminuisci W e H)
        "30x30-crea la tua grafica.jpg": [20.0, 15.0, 60.0, 70.0], 
    }

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- 2. MOTORE DI RENDERING PROFESSIONALE ---
def process_mockup(tmpl_pil, cover_pil, t_name, blur_rad):
    tmpl_img = tmpl_pil.convert('RGB')
    tmpl_gray = tmpl_pil.convert('L')
    w_f, h_f = tmpl_img.size
    
    if t_name not in st.session_state.coords:
        st.session_state.coords[t_name] = [10.0, 10.0, 80.0, 80.0]
    
    px, py, pw, ph = st.session_state.coords[t_name]
    
    # Calcolo pixel esatti
    x1, y1 = int((px * w_f) / 100), int((py * h_f) / 100)
    tw, th = int((pw * w_f) / 100), int((ph * h_f) / 100)
    
    # Sicurezza: non uscire mai dai bordi del file originale
    tw = max(1, min(tw, w_f - x1))
    th = max(1, min(th, h_f - y1))
    
    # 1. Preparazione Shadow Map (Texture del libro)
    crop_gray = np.array(tmpl_gray.crop((x1, y1, x1+tw, y1+th))).astype(np.float64)
    # Moltiplicatore ombre (regolato su 255)
    shadow_map = np.expand_dims(np.clip(crop_gray / 255.0, 0.0, 1.0), axis=2)

    # 2. Resize Cover
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # 3. Maschera per bordi morbidi (Feathering)
    mask = Image.new("L", (tw, th), 255)
    if blur_rad > 0:
        draw = ImageDraw.Draw(mask)
        draw.rectangle([0, 0, tw, th], outline=0, width=int(blur_rad/2)+1)
        mask = mask.filter(ImageFilter.GaussianBlur(blur_rad))
    alpha = np.expand_dims(np.array(mask).astype(np.float64) / 255.0, axis=2)

    # 4. Blending finale (Multiply + Alpha Mix)
    crop_orig = np.array(tmpl_img.crop((x1, y1, x1+tw, y1+th))).astype(np.float64)
    # La cover prende le ombre, poi viene mischiata allo sfondo tramite alpha
    blended = ((cover_res * shadow_map) * alpha) + (crop_orig * (1 - alpha))
    
    final_np = np.array(tmpl_img).copy()
    final_np[y1:y1+th, x1:x1+tw] = np.clip(blended, 0, 255).astype(np.uint8)
    return Image.fromarray(final_np)

# --- 3. CARICAMENTO LIBRERIA ---
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
tab_prod, tab_sett = st.tabs(["🚀 PRODUZIONE BATCH", "⚙️ IMPOSTAZIONI"])

with tab_prod:
    c_l, c_r = st.columns([1, 2])
    with c_l:
        formato = st.radio("Seleziona Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
        sfoca = st.slider("Morbidezza bordi:", 0.0, 15.0, 5.0, 0.5)
        if st.button("🗑️ RESET"):
            st.session_state.uploader_key += 1
            st.rerun()
    with c_r:
        disegni = st.file_uploader("Carica le tue copertine:", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

    if disegni and libreria[formato]:
        if st.button("🚀 GENERA ZIP"):
            z_io = io.BytesIO()
            with zipfile.ZipFile(z_io, "a") as zf:
                for d in disegni:
                    d_img = Image.open(d)
                    for t_n, t_i in libreria[formato].items():
                        res = process_mockup(t_i, d_img, t_n, sfoca)
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zf.writestr(f"{os.path.splitext(d.name)[0]}/{t_n}.jpg", buf.getvalue())
            st.download_button("📥 SCARICA ZIP", z_io.getvalue(), "Mockups.zip")
        
        # Anteprima dell'ultimo caricato
        t_pre_n = list(libreria[formato].keys())[0]
        st.subheader(f"Anteprima su {t_pre_n}")
        st.image(process_mockup(libreria[formato][t_pre_n], Image.open(disegni[-1]), t_pre_n, sfoca), use_column_width=True)

with tab_sett:
    st.subheader("🛠️ Calibratore di Precisione")
    if libreria["Tutti"]:
        t_mod = st.selectbox("Template da regolare:", list(libreria["Tutti"].keys()))
        if t_mod not in st.session_state.coords:
            st.session_state.coords[t_mod] = [10.0, 10.0, 80.0, 80.0]
            
        c_in, c_pre = st.columns([1, 2])
        with c_in:
            st.info("⚠️ Se l'immagine è troppo grande, diminuisci W% e H%.")
            st.session_state.coords[t_mod][0] = st.number_input("X % (Posiz. Orizzontale)", value=st.session_state.coords[t_mod][0], step=0.1)
            st.session_state.coords[t_mod][1] = st.number_input("Y % (Posiz. Verticale)", value=st.session_state.coords[t_mod][1], step=0.1)
            st.session_state.coords[t_mod][2] = st.number_input("W % (Larghezza Immagine)", value=st.session_state.coords[t_mod][2], step=0.1)
            st.session_state.coords[t_mod][3] = st.number_input("H % (Altezza Immagine)", value=st.session_state.coords[t_mod][3], step=0.1)
            t_test = st.file_uploader("Carica immagine di test:", type=['jpg', 'png'], key="test_sett")
            st.code(f"'{t_mod}': {st.session_state.coords[t_mod]},")
        with c_pre:
            if t_test:
                st.image(process_mockup(libreria["Tutti"][t_mod], Image.open(t_test), t_mod, 5.0), use_column_width=True)
            else:
                st.warning("Carica una cover di test per vedere la calibrazione.")

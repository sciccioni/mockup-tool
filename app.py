import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import os
import io
import zipfile

# --- 1. CONFIGURAZIONE E COORDINATE ---
st.set_page_config(page_title="PhotoBook Master V5.7", layout="wide")

if 'coords' not in st.session_state:
    st.session_state.coords = {
        "base_copertina_verticale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_copertina_orizzontale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_verticale_temi_app.jpg": [34.6, 9.2, 30.2, 80.3],
        "base_bottom_app.jpg": [21.9, 4.9, 56.5, 91.3],
        "base_orizzontale_temi_app.jpg": [18.9, 9.4, 61.8, 83.0],
        "base_orizzontale_temi_app3.jpg": [18.7, 9.4, 62.2, 82.6],
        "base_quadrata_temi_app.jpg": [27.8, 10.8, 44.5, 79.0],
    }

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- 2. MOTORE DI RENDERING (Shadows + Feathering) ---
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
    
    # Recupero coordinate dal session_state
    if t_name in st.session_state.coords:
        px, py, pw, ph = st.session_state.coords[t_name]
    else:
        # Fallback se il template è nuovo
        px, py, pw, ph = 5.0, 5.0, 90.0, 90.0
        st.session_state.coords[t_name] = [px, py, pw, ph]

    x1, y1 = int((px * w) / 100), int((py * h) / 100)
    tw, th = int((pw * w) / 100), int((ph * h) / 100)
    
    # Resize cover
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # Shadow Map (Sempre attiva per il realismo)
    # Se il template è bianco, shadow_map sarà ~1.0 (nessun effetto)
    # Se il template ha ombre, shadow_map le applicherà alla cover
    shadow_map = np.clip(tmpl_gray[y1:y1+th, x1:x1+tw] / 255.0, 0.0, 1.0)
    shadow_map = np.expand_dims(shadow_map, axis=2)

    # Maschera per bordi morbidi
    f_mask = get_feathered_mask((tw, th), blur_rad)
    alpha = np.array(f_mask).astype(np.float64) / 255.0
    alpha = np.expand_dims(alpha, axis=2)

    # Mix Finale: (Cover * Ombre) + Sfondo Originale (tramite Alpha Mask)
    orig_area = tmpl_rgb[y1:y1+th, x1:x1+tw]
    cover_final = cover_res * shadow_map
    blended = (cover_final * alpha) + (orig_area * (1 - alpha))
    
    result = tmpl_rgb.copy()
    result[y1:y1+th, x1:x1+tw] = blended
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- 3. SMISTAMENTO TEMPLATE ---
def get_manual_cat(filename):
    fn = filename.lower()
    # VERTICALI
    if any(x in fn for x in ["verticale", "bottom", "15x22", "20x30"]):
        return "Verticali"
    # ORIZZONTALI (Inclusi 32x24 e 40x30)
    if any(x in fn for x in ["orizzontale", "20x15", "27x20", "32x24", "40x30"]):
        return "Orizzontali"
    # QUADRATI (Incluso 30x30)
    if any(x in fn for x in ["quadrata", "20x20", "30x30", "crea la tua grafica"]):
        return "Quadrati"
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

# --- 4. INTERFACCIA UTENTE ---
st.title("📖 PhotoBook Master V5.7")

tab_prod, tab_sett = st.tabs(["🚀 PRODUZIONE BATCH", "⚙️ IMPOSTAZIONI TEMPLATE"])

# --- TAB PRODUZIONE ---
with tab_prod:
    c_ctrl, c_up = st.columns([1, 2])
    with c_ctrl:
        formato = st.radio("Scegli Categoria:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
        blur_val = st.slider("Morbidezza Bordi (px):", 0.0, 15.0, 5.0, 0.5)
        if st.button("🗑️ RESET DESIGN"):
            st.session_state.uploader_key += 1
            st.rerun()
    
    with c_up:
        disegni = st.file_uploader("Carica le copertine:", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

    if disegni and libreria[formato]:
        if st.button("🚀 GENERA TUTTI I MOCKUP"):
            zip_io = io.BytesIO()
            with zipfile.ZipFile(zip_io, "a") as zf:
                bar = st.progress(0)
                targets = libreria[formato]
                total = len(disegni) * len(targets)
                curr = 0
                for d_file in disegni:
                    d_img = Image.open(d_file)
                    d_fn = os.path.splitext(d_file.name)[0]
                    for t_name, t_img in targets.items():
                        res = process_mockup(t_img, d_img, t_name, blur_val)
                        if res:
                            buf = io.BytesIO()
                            res.save(buf, format='JPEG', quality=95)
                            zf.writestr(f"{d_fn}/{t_name}.jpg", buf.getvalue())
                        curr += 1
                        bar.progress(curr/total)
            st.download_button("📥 SCARICA ZIP", zip_io.getvalue(), "Mockups_Batch.zip")

        # Anteprima dinamica
        t_pre = list(libreria[formato].keys())[0]
        st.subheader(f"Anteprima su {t_pre}")
        st.image(process_mockup(libreria[formato][t_pre], Image.open(disegni[-1]), t_pre, blur_val), use_column_width=True)

# --- TAB IMPOSTAZIONI ---
with tab_sett:
    st.subheader("🛠️ Calibrazione Coordinate (Con Blending Attivo)")
    col_sel, col_in = st.columns([1, 1])
    
    with col_sel:
        t_mod = st.selectbox("Seleziona template:", list(libreria["Tutti"].keys()))
        t_cov = st.file_uploader("Carica cover di test:", type=['jpg', 'png'], key="cov_test")
        blur_test = st.slider("Test Sfocatura (px):", 0.0, 15.0, 5.0, 0.5, key="blur_sett")
        
    with col_in:
        c1, c2 = st.columns(2)
        st.session_state.coords[t_mod][0] = c1.number_input("X %", value=st.session_state.coords[t_mod][0], step=0.1)
        st.session_state.coords[t_mod][2] = c1.number_input("W %", value=st.session_state.coords[t_mod][2], step=0.1)
        st.session_state.coords[t_mod][1] = c2.number_input("Y %", value=st.session_state.coords[t_mod][1], step=0.1)
        st.session_state.coords[t_mod][3] = c2.number_input("H %", value=st.session_state.coords[t_mod][3], step=0.1)
        st.info("Regola i parametri per far combaciare la cover al libro. Le ombre sono attive per aiutarti a vedere le texture.")
        st.code(f"'{t_mod}': {st.session_state.coords[t_mod]},")

    if t_cov:
        st.divider()
        st.image(process_mockup(libreria["Tutti"][t_mod], Image.open(t_cov), t_mod, blur_test), use_column_width=True)

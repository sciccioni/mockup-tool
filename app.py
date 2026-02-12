import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import os
import io
import zipfile

# --- 1. SETUP INIZIALE ---
st.set_page_config(page_title="PhotoBook Master Pro V4.7 (White Fix)", layout="wide")

# Coordinate iniziali (incluse quelle statiche per i piatti)
if 'coords' not in st.session_state:
    st.session_state.coords = {
        "base_verticale_temi_app.jpg": [34.6, 9.2, 30.2, 80.3],
        "base_bottom_app.jpg": [21.9, 4.9, 56.5, 91.3],
        "base_orizzontale_temi_app.jpg": [18.9, 9.4, 61.8, 83.0],
        "base_orizzontale_temi_app3.jpg": [18.7, 9.4, 62.2, 82.6],
        "base_quadrata_temi_app.jpg": [27.8, 10.8, 44.5, 79.0],
        "base_copertina_verticale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_copertina_orizzontale.jpg": [0.0, 0.0, 100.0, 100.0], # <--- AGGIUNTO STATICO
    }

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- 2. FUNZIONI TECNICHE ---
def get_feathered_mask(size, blur_radius):
    mask = Image.new("L", size, 255)
    if blur_radius > 0:
        draw = ImageDraw.Draw(mask)
        draw.rectangle([0, 0, size[0], size[1]], outline=0, width=int(blur_radius/2) + 1)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    return mask

def process_mockup(tmpl_pil, cover_pil, t_name, blur_rad):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    
    is_static_cover = False # Flag per disabilitare ombre

    if t_name in st.session_state.coords:
        px, py, pw, ph = st.session_state.coords[t_name]
        x1, y1 = int((px * w) / 100), int((py * h) / 100)
        tw, th = int((pw * w) / 100), int((ph * h) / 100)
        face_val = 255.0
        # FIX: Se le coordinate sono 0,0,100,100, è una cover statica
        if px == 0.0 and py == 0.0 and pw == 100.0 and ph == 100.0:
            is_static_cover = True
    else:
        # Fallback Auto
        corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
        bg_val = np.median(corners)
        book_mask = tmpl_gray > (bg_val + 3)
        coords = np.argwhere(book_mask)
        if coords.size == 0: return None
        y1, x1 = coords.min(axis=0)
        y2, x2 = coords.max(axis=0)
        tw, th = x2 - x1 + 1, y2 - y1 + 1
        face_val = 246.0

    # Resize Cover
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # Maschera Sfumatura
    feather_mask = get_feathered_mask((tw, th), blur_rad)
    alpha = np.array(feather_mask).astype(np.float64) / 255.0
    alpha = np.expand_dims(alpha, axis=2)

    # FIX: Shadow Map Condizionale
    if is_static_cover:
        # Se è statico, nessuna ombra (tutto 1.0)
        shadow_map = np.ones((th, tw, 1), dtype=np.float64)
    else:
        # Altrimenti calcola le ombre normalmente
        shadow_map = np.clip(tmpl_gray[y1:y1+th, x1:x1+tw] / face_val, 0, 1.0)
        shadow_map = np.expand_dims(shadow_map, axis=2)

    # Composizione
    orig_area = tmpl_rgb[y1:y1+th, x1:x1+tw]
    final_cover = cover_res * shadow_map
    blended = (final_cover * alpha) + (orig_area * (1 - alpha))
    
    result = tmpl_rgb.copy()
    result[y1:y1+th, x1:x1+tw] = blended
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

@st.cache_data
def load_lib():
    path = "templates"
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}, "Tutti": {}}
    if os.path.exists(path):
        for f in os.listdir(path):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                lib["Tutti"][f] = Image.open(os.path.join(path, f))
                fn = f.lower()
                if any(x in fn for x in ["verticale", "bottom", "15x22"]): lib["Verticali"][f] = lib["Tutti"][f]
                elif any(x in fn for x in ["orizzontale", "20x15", "27x20"]): lib["Orizzontali"][f] = lib["Tutti"][f]
                elif any(x in fn for x in ["quadrata", "20x20"]): lib["Quadrati"][f] = lib["Tutti"][f]
    return lib

libreria = load_lib()

# --- 3. INTERFACCIA ---
st.title("📖 PhotoBook Master V4.7 (Fixed White Issue)")

tab_prod, tab_sett = st.tabs(["🚀 PRODUZIONE BATCH", "⚙️ IMPOSTAZIONI TEMPLATE"])

# --- TAB PRODUZIONE ---
with tab_prod:
    col_ctrl, col_up = st.columns([1, 2])
    with col_ctrl:
        formato = st.radio("Categoria:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
        blur_val = st.slider("Sfocatura Bordi (px):", 0.0, 15.0, 5.0, 0.5, key="prod_blur")
        if st.button("🗑️ SVUOTA DESIGN"):
            st.session_state.uploader_key += 1
            st.rerun()
    
    with col_up:
        disegni = st.file_uploader("Carica le copertine:", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

    if disegni and libreria[formato]:
        st.divider()
        if st.button("🚀 GENERA TUTTI E SCARICA ZIP"):
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

        # Anteprima veloce
        t_preview = list(libreria[formato].keys())[0]
        st.subheader(f"👁️ Anteprima rapida su {t_preview}")
        st.image(process_mockup(libreria[formato][t_preview], Image.open(disegni[-1]), t_preview, blur_val), use_column_width=True)

# --- TAB IMPOSTAZIONI ---
with tab_sett:
    st.subheader("🛠️ Calibrazione e Coordinate")
    col_sel, col_inputs = st.columns([1, 1])
    with col_sel:
        t_da_mod = st.selectbox("Seleziona template:", list(libreria["Tutti"].keys()))
        test_cover = st.file_uploader("Carica cover di test:", type=['jpg', 'png'])
        if t_da_mod not in st.session_state.coords:
            st.session_state.coords[t_da_mod] = [0.0, 0.0, 100.0, 100.0]

    with col_inputs:
        c1, c2 = st.columns(2)
        with c1:
            st.session_state.coords[t_da_mod][0] = st.number_input("X Start %", value=st.session_state.coords[t_da_mod][0], step=0.1)
            st.session_state.coords[t_da_mod][2] = st.number_input("Larghezza %", value=st.session_state.coords[t_da_mod][2], step=0.1)
        with c2:
            st.session_state.coords[t_da_mod][1] = st.number_input("Y Start %", value=st.session_state.coords[t_da_mod][1], step=0.1)
            st.session_state.coords[t_da_mod][3] = st.number_input("Altezza %", value=st.session_state.coords[t_da_mod][3], step=0.1)
        st.warning("Imposta X=0, Y=0, W=100, H=100 per i template piatti (statici) per evitare immagini bianche.")
        st.code(f"'{t_da_mod}': {st.session_state.coords[t_da_mod]},")

    if test_cover:
        st.divider()
        st.subheader("Preview Calibrazione")
        res_test = process_mockup(libreria["Tutti"][t_da_mod], Image.open(test_cover), t_da_mod, 5.0)
        st.image(res_test, use_column_width=True)

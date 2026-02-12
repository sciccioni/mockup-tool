import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import os
import io
import zipfile

# --- 1. SETUP E COORDINATE DEFINITIVE ---
st.set_page_config(page_title="PhotoBook Master Pro V4.8", layout="wide")

if 'coords' not in st.session_state:
    st.session_state.coords = {
        # Template Piatti (100% statici con Blending)
        "base_copertina_verticale.jpg": [0.0, 0.0, 100.0, 100.0],
        "base_copertina_orizzontale.jpg": [0.0, 0.0, 100.0, 100.0],
        # Template App (Coordinate calibrate)
        "base_verticale_temi_app.jpg": [34.6, 9.2, 30.2, 80.3],
        "base_bottom_app.jpg": [21.9, 4.9, 56.5, 91.3],
        "base_orizzontale_temi_app.jpg": [18.9, 9.4, 61.8, 83.0],
        "base_orizzontale_temi_app3.jpg": [18.7, 9.4, 62.2, 82.6],
        "base_quadrata_temi_app.jpg": [27.8, 10.8, 44.5, 79.0],
    }

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- 2. FUNZIONI TECNICHE ---
def get_feathered_mask(size, blur_radius):
    """Crea la maschera per sfumare i bordi (5px default)."""
    mask = Image.new("L", size, 255)
    if blur_radius > 0:
        draw = ImageDraw.Draw(mask)
        # Rientro per non far 'sbordare' il blur all'esterno
        offset = int(blur_radius / 2) + 1
        draw.rectangle([0, 0, size[0], size[1]], outline=0, width=offset)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    return mask

def process_mockup(tmpl_pil, cover_pil, t_name, blur_rad):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    
    # 1. Recupero Coordinate
    if t_name in st.session_state.coords:
        px, py, pw, ph = st.session_state.coords[t_name]
        x1, y1 = int((px * w) / 100), int((py * h) / 100)
        tw, th = int((pw * w) / 100), int((ph * h) / 100)
        # Per i fissi usiamo 255 come riferimento bianco puro
        face_val = 255.0
    else:
        # Fallback automatico per altri file
        corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
        bg_val = np.median(corners)
        book_mask = tmpl_gray > (bg_val + 3)
        coords = np.argwhere(book_mask)
        if coords.size == 0: return None
        y1, x1 = coords.min(axis=0)
        y2, x2 = coords.max(axis=0)
        tw, th = x2 - x1 + 1, y2 - y1 + 1
        face_val = 246.0

    # 2. Resize Cover
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # 3. Maschera Sfumatura (Feathering)
    f_mask = get_feathered_mask((tw, th), blur_rad)
    alpha = np.array(f_mask).astype(np.float64) / 255.0
    alpha = np.expand_dims(alpha, axis=2)

    # 4. Shadow Map (Blending Multiply) - QUESTO È IL MOTORE DEL REALISMO
    # Calcoliamo quanto il template è scuro rispetto al bianco e lo applichiamo alla cover
    shadow_map = np.clip(tmpl_gray[y1:y1+th, x1:x1+tw] / face_val, 0.0, 1.0)
    shadow_map = np.expand_dims(shadow_map, axis=2)

    # 5. Fusione Finale
    # Applichiamo le ombre alla cover, poi la fondiamo con lo sfondo usando l'alpha (blur)
    orig_area = tmpl_rgb[y1:y1+th, x1:x1+tw]
    cover_with_shadows = cover_res * shadow_map
    
    # Mix tra cover (con ombre) e template originale basato sui bordi sfumati
    blended = (cover_with_shadows * alpha) + (orig_area * (1 - alpha))
    
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
                img = Image.open(os.path.join(path, f))
                lib["Tutti"][f] = img
                fn = f.lower()
                if any(x in fn for x in ["verticale", "bottom", "15x22"]): lib["Verticali"][f] = img
                elif any(x in fn for x in ["orizzontale", "20x15", "27x20"]): lib["Orizzontali"][f] = img
                elif any(x in fn for x in ["quadrata", "20x20"]): lib["Quadrati"][f] = img
    return lib

libreria = load_lib()

# --- 3. INTERFACCIA ---
st.title("📖 PhotoBook Master V4.8 (Full Blending + Blur)")

tab_prod, tab_sett = st.tabs(["🚀 PRODUZIONE BATCH", "⚙️ IMPOSTAZIONI TEMPLATE"])

with tab_prod:
    c_ctrl, c_up = st.columns([1, 2])
    with c_ctrl:
        formato = st.radio("Categoria:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
        blur_val = st.slider("Sfocatura Bordi (px):", 0.0, 15.0, 5.0, 0.5)
        if st.button("🗑️ SVUOTA DESIGN"):
            st.session_state.uploader_key += 1
            st.rerun()
    
    with c_up:
        disegni = st.file_uploader("Carica copertine:", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

    if disegni and libreria[formato]:
        st.divider()
        if st.button("🚀 GENERA E SCARICA ZIP"):
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
            st.download_button("📥 SCARICA ZIP", zip_io.getvalue(), "Mockups_Finali.zip")

        t_pre = list(libreria[formato].keys())[0]
        st.subheader(f"Anteprima su {t_pre}")
        st.image(process_mockup(libreria[formato][t_pre], Image.open(disegni[-1]), t_pre, blur_val), use_column_width=True)

with tab_sett:
    st.subheader("🛠️ Calibrazione")
    c_sel, c_in = st.columns([1, 1])
    with c_sel:
        t_mod = st.selectbox("Template:", list(libreria["Tutti"].keys()))
        t_cov = st.file_uploader("Cover test:", type=['jpg', 'png'])
    with c_in:
        c1, c2 = st.columns(2)
        st.session_state.coords[t_mod][0] = c1.number_input("X Start %", value=st.session_state.coords[t_mod][0], step=0.1)
        st.session_state.coords[t_mod][2] = c1.number_input("Larghezza %", value=st.session_state.coords[t_mod][2], step=0.1)
        st.session_state.coords[t_mod][1] = c2.number_input("Y Start %", value=st.session_state.coords[t_mod][1], step=0.1)
        st.session_state.coords[t_mod][3] = c2.number_input("Altezza %", value=st.session_state.coords[t_mod][3], step=0.1)
        st.code(f"'{t_mod}': {st.session_state.coords[t_mod]},")
    if t_cov:
        st.image(process_mockup(libreria["Tutti"][t_mod], Image.open(t_cov), t_mod, 5.0), use_column_width=True)

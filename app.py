import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import os
import io
import zipfile

# --- 1. CONFIGURAZIONE E COORDINATE DEFINITIVE ---
st.set_page_config(page_title="PhotoBook Production V4.3 - Soft Edges", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# Le tue coordinate calibrate
TEMPLATE_MAPS = {
    "base_copertina_verticale.jpg": (0.0, 0.0, 100.0, 100.0),
    "base_verticale_temi_app.jpg": (34.6, 9.2, 30.2, 80.3),
    "base_bottom_app.jpg": (21.9, 4.9, 56.5, 91.3),
    "base_orizzontale_temi_app.jpg": (18.9, 9.4, 61.8, 83.0),
    "base_orizzontale_temi_app3.jpg": (18.7, 9.4, 62.2, 82.6),
    "base_quadrata_temi_app.jpg": (27.8, 10.8, 44.5, 79.0),
}

# --- 2. FUNZIONE PER SFUMARE I BORDI (FEATHERING) ---
def get_feathered_mask(size, blur_radius=5):
    """Crea una maschera con i bordi sfumati per fondere la cover."""
    mask = Image.new("L", size, 255)
    draw = ImageDraw.Draw(mask)
    # Disegna un bordo nero sottile per permettere alla sfocatura di 'rientrare'
    draw.rectangle([0, 0, size[0], size[1]], outline=0, width=2)
    return mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))

# --- 3. LOGICA DI SMISTAMENTO ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["verticale", "bottom", "15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["orizzontale", "20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["quadrata", "20x20", "30x30"]): return "Quadrati"
    return "Altro"

# --- 4. MOTORE DI COMPOSIZIONE IBRIDO ---
def find_book_region_auto(tmpl_gray, bg_val):
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 3)
    rows = np.any(book_mask, axis=1)
    cols = np.any(book_mask, axis=0)
    if not rows.any() or not cols.any(): return None
    by1, by2 = np.where(rows)[0][[0, -1]]
    bx1, bx2 = np.where(cols)[0][[0, -1]]
    
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, bx1+margin:bx2-margin]
    face_val = float(np.median(face_area)) if face_area.size > 0 else 246.0
    return {'bx1': bx1, 'bx2': bx2, 'by1': by1, 'by2': by2, 'face_val': face_val}

def process_mockup(tmpl_pil, cover_pil, t_name):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    cover = cover_pil.convert('RGB')

    # Identificazione area
    if t_name in TEMPLATE_MAPS:
        px, py, pw, ph = TEMPLATE_MAPS[t_name]
        x1, y1 = int((px * w) / 100), int((py * h) / 100)
        tw, th = int((pw * w) / 100), int((ph * h) / 100)
        face_val = 255.0
    else:
        corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
        reg = find_book_region_auto(tmpl_gray, np.median(corners))
        if not reg: return None
        x1, y1 = reg['bx1'], reg['by1']
        tw, th = reg['bx2'] - x1 + 1, reg['by2'] - y1 + 1
        face_val = reg['face_val']

    # 1. Resize e preparazione cover
    c_res = np.array(cover.resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # 2. Creazione Maschera di Sfumatura (5px)
    feather_mask = get_feathered_mask((tw, th), blur_radius=5)
    feather_alpha = np.array(feather_mask).astype(np.float64) / 255.0
    feather_alpha = np.expand_dims(feather_alpha, axis=2) # Per i 3 canali RGB

    # 3. Shadow Map (Multiply)
    shadow_map = np.clip(tmpl_gray[y1:y1+th, x1:x1+tw] / face_val, 0, 1.0)
    shadow_map = np.expand_dims(shadow_map, axis=2)

    # 4. Composizione con fusione morbida
    # pixel_copertina = (cover * ombre)
    # pixel_finali = (pixel_copertina * maschera_sfumata) + (pixel_originali * (1 - maschera_sfumata))
    
    target_area_orig = tmpl_rgb[y1:y1+th, x1:x1+tw]
    cover_applied = c_res * shadow_map
    
    blended_area = (cover_applied * feather_alpha) + (target_area_orig * (1 - feather_alpha))
    
    result = tmpl_rgb.copy()
    result[y1:y1+th, x1:x1+tw] = blended_area
    
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- 5. INTERFACCIA STREAMLIT ---
st.title("📖 PhotoBook Production - V4.3 Soft Edges")

@st.cache_data
def load_library():
    path = "templates"
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    if os.path.exists(path):
        for f in os.listdir(path):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                cat = get_manual_cat(f)
                if cat in lib: lib[cat][f] = Image.open(os.path.join(path, f))
    return lib

libreria = load_library()

tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])
for i, (tab, name) in enumerate(zip(tabs, ["Verticali", "Orizzontali", "Quadrati"])):
    with tab:
        cols = st.columns(5)
        for idx, f_name in enumerate(libreria[name].keys()):
            cols[idx % 5].image(libreria[name][f_name], caption=f_name, use_column_width=True)

st.divider()

st.subheader("🚀 Produzione in Batch (Sfumatura 5px)")
col_sel, col_del = st.columns([3, 1])

with col_sel:
    categoria = st.radio("Seleziona Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)

with col_del:
    if st.button("🗑️ SVUOTA DESIGN"):
        st.session_state.uploader_key += 1
        st.rerun()

disegni = st.file_uploader(f"Carica i design:", 
                           accept_multiple_files=True, 
                           key=f"up_{st.session_state.uploader_key}")

if disegni and libreria[categoria]:
    if st.button("🚀 GENERA TUTTI I MOCKUP"):
        zip_io = io.BytesIO()
        with zipfile.ZipFile(zip_io, "a") as zf:
            bar = st.progress(0)
            target_list = libreria[categoria]
            total_ops = len(disegni) * len(target_list)
            curr = 0
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                for t_name, t_img in target_list.items():
                    res = process_mockup(t_img, d_img, t_name)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zf.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    curr += 1
                    bar.progress(curr / total_ops)
        st.success("✅ Completato!")
        st.download_button("📥 SCARICA ZIP", zip_io.getvalue(), f"Mockups_Sfumati.zip")

    st.divider()
    st.subheader("👁️ Anteprima con Sfumatura")
    t_test_name = list(libreria[categoria].keys())[0]
    preview = process_mockup(libreria[categoria][t_test_name], Image.open(disegni[-1]), t_test_name)
    st.image(preview, caption=f"Effetto sfumato su {t_test_name}", use_column_width=True)

import streamlit as st
import numpy as np
from PIL import Image
import os
import io
import zipfile

# --- 1. COORDINATE FISSE SOLO PER I TEMPLATE "APP" ---
# Questa è la "nuova" parte che risolve il problema dei libri bianchi
TEMPLATE_MAPS = {
    "base_verticale_temi_app": (35.1, 10.4, 29.8, 79.2),
    "base_orizzontale_temi_app": (19.4, 9.4, 61.2, 81.2),
    "base_orizzontale_temi_app3": (19.4, 9.4, 61.2, 81.2),
    "base_quadrata_temi_app": (28.2, 10.4, 43.6, 77.4),
    "base_bottom_app": (22.8, 4.4, 54.8, 89.6),
}

# --- 2. LOGICA ORIGINALE (VECCHIA APP) ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["base_copertina_verticale", "base_verticale_temi_app", "base_bottom_app", "15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["base_copertina_orizzontale", "base_orizzontale_temi_app", "20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["base_quadrata_temi_app", "20x20", "30x30"]): return "Quadrati"
    return "Altro"

def find_book_region(tmpl_gray, bg_val):
    """Logica di rilevamento bordi 'As Is' della vecchia versione"""
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 3)
    rows = np.any(book_mask, axis=1)
    cols = np.any(book_mask, axis=0)
    if not rows.any() or not cols.any(): return None
    by1, by2 = np.where(rows)[0][[0, -1]]
    bx1, bx2 = np.where(cols)[0][[0, -1]]
    
    # Normalizzazione luminosità faccia
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, bx1+margin:bx2-margin]
    face_val = float(np.median(face_area)) if face_area.size > 0 else 246.0
    return {'bx1': bx1, 'bx2': bx2, 'by1': by1, 'by2': by2, 'face_val': face_val}

# --- 3. MOTORE DI COMPOSIZIONE IBRIDO ---
def process_mockup(tmpl_pil, cover_pil, t_name):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    cover = cover_pil.convert('RGB')

    # CONTROLLO: Se il file è un "app", usa le coordinate fisse
    app_key = next((k for k in TEMPLATE_MAPS.keys() if k in t_name.lower()), None)

    if app_key:
        # LOGICA NUOVA (PRECISIONE)
        px, py, pw, ph = TEMPLATE_MAPS[app_key]
        x1, y1 = int((px * w) / 100), int((py * h) / 100)
        tw, th = int((pw * w) / 100), int((ph * h) / 100)
        c_res = np.array(cover.resize((tw, th), Image.LANCZOS)).astype(np.float64)
        
        # Shadow Map (Multiply)
        book_shadows = tmpl_gray[y1:y1+th, x1:x1+tw]
        shadow_map = np.clip(book_shadows / 255.0, 0, 1.0)
        
        result = tmpl_rgb.copy()
        for c in range(3):
            result[y1:y1+th, x1:x1+tw, c] = c_res[:, :, c] * shadow_map
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

    else:
        # LOGICA VECCHIA (AUTOMATICA)
        corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
        bg_val = np.median(corners)
        reg = find_book_region(tmpl_gray, bg_val)
        if reg is None: return None
        
        tw, th = reg['bx2'] - reg['bx1'] + 1, reg['by2'] - reg['by1'] + 1
        c_res = np.array(cover.resize((tw, th), Image.LANCZOS)).astype(np.float64)
        ratio = np.clip(tmpl_gray[reg['by1']:reg['by2']+1, reg['bx1']:reg['bx2']+1] / reg['face_val'], 0, 1.0)
        
        result = tmpl_rgb.copy()
        for c in range(3):
            result[reg['by1']:reg['by2']+1, reg['bx1']:reg['bx2']+1, c] = c_res[:, :, c] * ratio
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- 4. INTERFACCIA STREAMLIT (Libreria a Tab) ---
st.set_page_config(page_title="PhotoBook Mockup V4 Ibrida", layout="wide")
st.title("📖 PhotoBook Mockup - Sistema Completo")

@st.cache_data
def load_lib():
    path = "templates"
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    if os.path.exists(path):
        for f in os.listdir(path):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                cat = get_manual_cat(f)
                if cat in lib: lib[cat][f] = Image.open(os.path.join(path, f))
    return lib

libreria = load_lib()

# Visualizzazione Libreria
tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])
for i, (tab, name) in enumerate(zip(tabs, ["Verticali", "Orizzontali", "Quadrati"])):
    with tab:
        cols = st.columns(4)
        for idx, f_name in enumerate(libreria[name].keys()):
            cols[idx % 4].image(libreria[name][f_name], caption=f_name, use_column_width=True)

st.divider()

# Produzione
st.subheader("🚀 Produzione")
c_fmt, c_up = st.columns([1, 3])
with c_fmt:
    scelta = st.radio("Formato:", ["Verticali", "Orizzontali", "Quadrati"])
with c_up:
    disegni = st.file_uploader(f"Carica copertine per {scelta}", accept_multiple_files=True)

if st.button("🚀 GENERA TUTTO") and disegni:
    zip_io = io.BytesIO()
    with zipfile.ZipFile(zip_io, "a") as zf:
        bar = st.progress(0)
        target_tmpls = libreria[scelta]
        total = len(disegni) * len(target_tmpls)
        count = 0
        for d_file in disegni:
            d_img = Image.open(d_file)
            for t_name, t_img in target_tmpls.items():
                res = process_mockup(t_img, d_img, t_name)
                if res:
                    buf = io.BytesIO()
                    res.save(buf, format='JPEG', quality=95)
                    zf.writestr(f"{os.path.splitext(d_file.name)[0]}/{t_name}.jpg", buf.getvalue())
                count += 1
                bar.progress(count / total)
    st.success("✅ Fatto!")
    st.download_button("📥 Scarica ZIP", zip_io.getvalue(), f"Mockup_{scelta}.zip")

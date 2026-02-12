import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import os
import io
import zipfile

# --- 1. CONFIGURAZIONE E COORDINATE DEFINITIVE (LE TUE CALIBRAZIONI) ---
st.set_page_config(page_title="PhotoBook Master Pro V4.5", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

TEMPLATE_MAPS = {
    "base_verticale_temi_app.jpg": (34.6, 9.2, 30.2, 80.3),
    "base_bottom_app.jpg": (21.9, 4.9, 56.5, 91.3),
    "base_orizzontale_temi_app.jpg": (18.9, 9.4, 61.8, 83.0),
    "base_orizzontale_temi_app3.jpg": (18.7, 9.4, 62.2, 82.6),
    "base_quadrata_temi_app.jpg": (27.8, 10.8, 44.5, 79.0),
    "base_copertina_verticale.jpg": (0.0, 0.0, 100.0, 100.0),
}

# --- 2. FUNZIONI TECNICHE (SFUMATURA E MOTORE) ---
def get_feathered_mask(size, blur_radius):
    """Crea una maschera alfa per sfumare i bordi della cover."""
    mask = Image.new("L", size, 255)
    if blur_radius > 0:
        draw = ImageDraw.Draw(mask)
        # Rientro di sicurezza per la sfocatura
        draw.rectangle([0, 0, size[0], size[1]], outline=0, width=int(blur_radius/2) + 1)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    return mask

def find_book_region_auto(tmpl_gray, bg_val):
    """Fallback automatico se il template non è mappato."""
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
    return {'x': bx1, 'y': by1, 'w': bx2 - bx1 + 1, 'h': by2 - by1 + 1, 'face_val': face_val}

def process_mockup(tmpl_pil, cover_pil, t_name, blur_rad):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    
    # Scelta coordinate: Mappa o Auto
    if t_name in TEMPLATE_MAPS:
        px, py, pw, ph = TEMPLATE_MAPS[t_name]
        x1, y1 = int((px * w) / 100), int((py * h) / 100)
        tw, th = int((pw * w) / 100), int((ph * h) / 100)
        face_val = 255.0
    else:
        corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
        reg = find_book_region_auto(tmpl_gray, np.median(corners))
        if not reg: return None
        x1, y1, tw, th, face_val = reg['x'], reg['y'], reg['w'], reg['h'], reg['face_val']

    # Elaborazione grafica
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # Maschera Sfumatura
    feather_mask = get_feathered_mask((tw, th), blur_rad)
    alpha = np.array(feather_mask).astype(np.float64) / 255.0
    alpha = np.expand_dims(alpha, axis=2)

    # Shadow Map
    shadow_map = np.clip(tmpl_gray[y1:y1+th, x1:x1+tw] / face_val, 0, 1.0)
    shadow_map = np.expand_dims(shadow_map, axis=2)

    # Composizione (Originale + (Cover * Ombre)) con Alpha Blending
    orig_area = tmpl_rgb[y1:y1+th, x1:x1+tw]
    final_cover = cover_res * shadow_map
    blended = (final_cover * alpha) + (orig_area * (1 - alpha))
    
    result = tmpl_rgb.copy()
    result[y1:y1+th, x1:x1+tw] = blended
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- 3. INTERFACCIA ---
st.title("📖 PhotoBook Master Production - V4.5")

@st.cache_data
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["verticale", "bottom", "15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["orizzontale", "20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["quadrata", "20x20", "30x30"]): return "Quadrati"
    return "Altro"

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

# Visualizzazione tab
tabs = st.tabs(["📂 Verticali", "📂 Orizzontali", "📂 Quadrati"])
for i, (tab, name) in enumerate(zip(tabs, ["Verticali", "Orizzontali", "Quadrati"])):
    with tab:
        cols = st.columns(5)
        for idx, f_name in enumerate(libreria[name].keys()):
            cols[idx % 5].image(libreria[name][f_name], caption=f_name, use_column_width=True)

st.divider()

# Produzione e controlli
st.subheader("🚀 Pannello di Produzione")
col_ctrl, col_up = st.columns([1, 2])

with col_ctrl:
    formato = st.radio("Scegli Categoria:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
    blur = st.slider("Morbidezza Bordi (Raggio Sfocatura):", 0.0, 20.0, 5.0, 0.5)
    
    if st.button("🗑️ SVUOTA TUTTI I DESIGN"):
        st.session_state.uploader_key += 1
        st.rerun()

with col_up:
    disegni = st.file_uploader("Carica le copertine:", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

if disegni and libreria[formato]:
    # Anteprima Affiancata (Nuova!)
    st.divider()
    t_test_name = list(libreria[formato].keys())[0]
    preview_img = process_mockup(libreria[formato][t_test_name], Image.open(disegni[-1]), t_test_name, blur)
    
    st.subheader(f"👁️ Anteprima Real-Time su {t_test_name}")
    col_pre1, col_pre2 = st.columns(2)
    with col_pre1:
        st.image(libreria[formato][t_test_name], caption="Mockup Originale", use_column_width=True)
    with col_pre2:
        st.image(preview_img, caption=f"Mockup con Sfumatura {blur}px", use_column_width=True)

    # Bottone di scaricamento
    st.divider()
    if st.button("🚀 GENERA BATCH COMPLETO"):
        zip_io = io.BytesIO()
        with zipfile.ZipFile(zip_io, "a", zipfile.ZIP_DEFLATED) as zf:
            bar = st.progress(0)
            target_list = libreria[formato]
            total = len(disegni) * len(target_list)
            curr = 0
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_fn = os.path.splitext(d_file.name)[0]
                for t_name, t_img in target_list.items():
                    res = process_mockup(t_img, d_img, t_name, blur)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zf.writestr(f"{d_fn}/{t_name}.jpg", buf.getvalue())
                    curr += 1
                    bar.progress(curr / total)
        st.success("✅ Pacchetto pronto!")
        st.download_button("📥 SCARICA ZIP", zip_io.getvalue(), f"Mockup_Batch_{formato}.zip")

import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageOps
import os
import io
import zipfile

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup - Smart Fit V4", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- COORDINATE FISSE PER TEMPLATE ---
# Formato: (x1, y1, x2, y2, face_value, bleed)
TEMPLATE_COORDS = {
    "base_copertina_verticale.jpg": (100, 80, 900, 1200, 246, 15),
    "base_verticale_temi_app.jpg": (150, 100, 850, 1150, 246, 15),
    "base_bottom_app.jpg": (120, 90, 880, 1180, 246, 15),
    "base_copertina_orizzontale.jpg": (80, 100, 1200, 900, 246, 15),
    "base_orizzontale_temi_app.jpg": (100, 120, 1180, 880, 246, 15),
    "base_quadrata_temi_app.jpg": (100, 100, 1000, 1000, 246, 15),
}

# --- SMISTAMENTO CATEGORIE ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["base_copertina_verticale", "base_verticale_temi_app", "base_bottom_app"]): return "Verticali"
    if any(x in fn for x in ["base_copertina_orizzontale", "base_orizzontale_temi_app"]): return "Orizzontali"
    if "base_quadrata_temi_app" in fn: return "Quadrati"
    if any(x in fn for x in ["15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["20x20", "30x30"]): return "Quadrati"
    return "Altro"

# --- LOGICA CORE CON COORDINATE FISSE ---
def composite_v4_fixed(tmpl_pil, cover_pil, template_name=""):
    # 1. SFOCATURA 1PX
    cover_pil = cover_pil.convert('RGB').filter(ImageFilter.GaussianBlur(radius=1))
    
    # Cerca coordinate fisse
    coords = None
    for key, values in TEMPLATE_COORDS.items():
        if key.lower() in template_name.lower():
            coords = values
            break
    
    # Se non trova coordinate fisse, usa il metodo automatico (fallback)
    if coords is None:
        return composite_v4_auto(tmpl_pil, cover_pil, template_name)
    
    bx1, by1, bx2, by2, face_val, bleed = coords
    
    tmpl = np.array(tmpl_pil).astype(np.float64)
    tmpl_gray = (0.299 * tmpl[:,:,0] + 0.587 * tmpl[:,:,1] + 0.114 * tmpl[:,:,2]) if tmpl.ndim == 3 else tmpl
    h, w = tmpl_gray.shape
    
    # Verifica che le coordinate siano valide per questo template
    if bx2 >= w or by2 >= h:
        st.warning(f"⚠️ Coordinate invalide per {template_name} (template: {w}x{h})")
        return composite_v4_auto(tmpl_pil, cover_pil, template_name)
    
    target_w = bx2 - bx1 + 1
    target_h = by2 - by1 + 1
    
    # --- SMART FIT ---
    full_w, full_h = target_w + bleed*2, target_h + bleed*2
    cover_fitted = ImageOps.fit(cover_pil, (full_w, full_h), method=Image.LANCZOS, centering=(0.5, 0.5))
    cover_res = np.array(cover_fitted).astype(np.float64)
    
    cover_final = cover_res[bleed:bleed+target_h, bleed:bleed+target_w]
    
    # VERIFICA DIMENSIONI
    if cover_final.shape[0] != target_h or cover_final.shape[1] != target_w:
        st.error(f"Mismatch dimensioni: cover_final={cover_final.shape}, target={target_h}x{target_w}")
        return None
    
    result = np.stack([tmpl_gray]*3, axis=2)
    
    # Estrai la region del libro dal template
    book_region = tmpl_gray[by1:by2+1, bx1:bx2+1]
    
    # VERIFICA COMPATIBILITA'
    if book_region.shape[0] != cover_final.shape[0] or book_region.shape[1] != cover_final.shape[1]:
        st.error(f"Shape mismatch: book_region={book_region.shape}, cover_final={cover_final.shape[:2]}")
        return None
    
    book_ratio = np.minimum(book_region / face_val, 1.0)
    
    for c in range(3):
        result[by1:by2+1, bx1:bx2+1, c] = cover_final[:, :, c] * book_ratio
            
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- METODO AUTOMATICO (FALLBACK) ---
def composite_v4_auto(tmpl_pil, cover_pil, template_name=""):
    cover_pil = cover_pil.convert('RGB').filter(ImageFilter.GaussianBlur(radius=1))
    
    tmpl = np.array(tmpl_pil).astype(np.float64)
    tmpl_gray = (0.299 * tmpl[:,:,0] + 0.587 * tmpl[:,:,1] + 0.114 * tmpl[:,:,2]) if tmpl.ndim == 3 else tmpl
    h, w = tmpl_gray.shape
    
    corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
    bg_val = float(np.median(corners))
    
    book_mask = tmpl_gray > (bg_val + 5)
    rows = np.any(book_mask, axis=1)
    cols = np.any(book_mask, axis=0)
    
    if not rows.any() or not cols.any(): 
        return None
    
    by1, by2 = np.where(rows)[0][[0, -1]]
    bx1, bx2 = np.where(cols)[0][[0, -1]]
    
    target_w, target_h = bx2 - bx1 + 1, by2 - by1 + 1
    bleed = 15
    
    full_w, full_h = target_w + bleed*2, target_h + bleed*2
    cover_fitted = ImageOps.fit(cover_pil, (full_w, full_h), method=Image.LANCZOS, centering=(0.5, 0.5))
    cover_res = np.array(cover_fitted).astype(np.float64)
    
    cover_final = cover_res[bleed:bleed+target_h, bleed:bleed+target_w]
    
    result = np.stack([tmpl_gray]*3, axis=2)
    book_region = tmpl_gray[by1:by2+1, bx1:bx2+1]
    book_ratio = np.minimum(book_region / 246.0, 1.0)
    
    for c in range(3):
        result[by1:by2+1, bx1:bx2+1, c] = cover_final[:, :, c] * book_ratio
            
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- CARICAMENTO ---
@st.cache_data
def load_templates():
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    if not os.path.exists("templates"): return lib
    for f in os.listdir("templates"):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            cat = get_manual_cat(f)
            if cat in lib: lib[cat][f] = Image.open(os.path.join("templates", f)).convert('RGB')
    return lib

libreria = load_templates()

# --- DEBUG HELPER ---
if st.sidebar.checkbox("🔍 Mostra dimensioni template"):
    for cat in ["Verticali", "Orizzontali", "Quadrati"]:
        st.sidebar.write(f"**{cat}:**")
        for t_name, t_img in libreria[cat].items():
            st.sidebar.write(f"  • {t_name}: {t_img.size[0]}x{t_img.size[1]}")

# --- INTERFACCIA ---
st.title("🚀 Mockup Engine - Fixed Coordinates V2")

col1, col2 = st.columns([2, 1])
with col1:
    scelta = st.radio("Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
with col2:
    if st.button("🗑️ Reset"):
        st.session_state.uploader_key += 1
        st.rerun()

disegni = st.file_uploader("Carica design", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

if st.button("🔥 GENERA E MOSTRA ANTEPRIME"):
    if not disegni or not libreria[scelta]:
        st.error("Mancano file o template!")
    else:
        target_tmpls = libreria[scelta]
        first_d = Image.open(disegni[0])
        
        st.subheader(f"🖼️ Anteprima: {disegni[0].name}")
        cols = st.columns(4)
        for idx, (t_name, t_img) in enumerate(target_tmpls.items()):
            prev = composite_v4_fixed(t_img, first_d, t_name)
            if prev:
                cols[idx % 4].image(prev, caption=t_name, use_column_width=True)
            else:
                cols[idx % 4].error(f"❌ {t_name}")

        # --- GENERAZIONE ZIP ---
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED) as zip_f:
            bar = st.progress(0)
            total = len(disegni) * len(target_tmpls)
            done = 0
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                for t_name, t_img in target_tmpls.items():
                    res = composite_v4_fixed(t_img, d_img, t_name)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zip_f.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    done += 1
                    bar.progress(done / total)
        
        st.success("Completato!")
        st.download_button("📥 SCARICA ZIP", zip_buf.getvalue(), f"Mockups_{scelta}.zip")

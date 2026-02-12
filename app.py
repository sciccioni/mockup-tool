import streamlit as st
import numpy as np
from PIL import Image, ImageFilter
import os
import io
import zipfile

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup Compositor - V3 Blur", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

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

# ===================================================================
# LOGICA V3 FIXED + SFOCATURA BORDI
# ===================================================================

def find_book_region(tmpl_gray, bg_val):
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 3)
    rows = np.any(book_mask, axis=1)
    cols = np.any(book_mask, axis=0)
    if not rows.any() or not cols.any(): return None
    by1, by2 = np.where(rows)[0][[0, -1]]
    bx1, bx2 = np.where(cols)[0][[0, -1]]
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    face_x1 = bx1
    for x in range(bx1, bx2 - 5):
        if np.all(row[x:x + 5] >= 240):
            face_x1 = x
            break
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area)) if face_area.size > 0 else 246.0
    return {'book_x1': int(bx1), 'book_x2': int(bx2), 'book_y1': int(by1), 'book_y2': int(by2), 'face_val': face_val}

def composite_v3_blur(tmpl_pil, cover_pil, template_name=""):
    # --- 1. APPLICO SFOCATURA 1px ALLA COVER ---
    # Applichiamo una leggera sfocatura per ammorbidire i bordi dell'immagine caricata
    cover_pil = cover_pil.convert('RGB').filter(ImageFilter.GaussianBlur(radius=1))
    
    tmpl = np.array(tmpl_pil).astype(np.float64)
    tmpl_gray = (0.299 * tmpl[:,:,0] + 0.587 * tmpl[:,:,1] + 0.114 * tmpl[:,:,2]) if tmpl.ndim == 3 else tmpl
    h, w = tmpl_gray.shape
    cover = np.array(cover_pil).astype(np.float64)
    
    corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
    bg_val = float(np.median(corners))
    region = find_book_region(tmpl_gray, bg_val)
    if region is None: return None
    
    bx1, bx2, by1, by2, face_val = region['book_x1'], region['book_x2'], region['book_y1'], region['book_y2'], region['face_val']
    target_w, target_h = bx2 - bx1 + 1, by2 - by1 + 1
    
    # Gestione Over-bleeding per basi piatte
    is_base = "base_copertina" in template_name.lower() or "temi_app" in template_name.lower()
    bleed = 15 if is_base else 12
    
    # Resize cover con bleed
    cover_res = np.array(Image.fromarray(cover.astype(np.uint8)).resize((target_w + bleed*2, target_h + bleed*2), Image.LANCZOS)).astype(np.float64)
    cover_final = cover_res[bleed:bleed+target_h, bleed:bleed+target_w]
    
    # Compositing
    result = np.stack([tmpl_gray]*3, axis=2)
    book_ratio = np.minimum(tmpl_gray[by1:by2+1, bx1:bx2+1] / face_val, 1.0)
    
    for c in range(3):
        result[by1:by2+1, bx1:bx2+1, c] = cover_final[:, :, c] * book_ratio
            
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- CARICAMENTO ---
@st.cache_data
def load_fixed_templates():
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    if not os.path.exists("templates"): return lib
    for f_name in os.listdir("templates"):
        if f_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            cat = get_manual_cat(f_name)
            if cat in lib:
                img = Image.open(os.path.join("templates", f_name)).convert('RGB')
                lib[cat][f_name] = img
    return lib

libreria = load_fixed_templates()

# --- INTERFACCIA ---
st.title("📖 PhotoBook Mockup - Blur 1px & Single Preview")

scelta = st.radio("Seleziona formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)

disegni = st.file_uploader(f"Carica design", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

if st.button("🚀 GENERA TUTTI"):
    if not disegni or not libreria[scelta]:
        st.error("Mancano i file!")
    else:
        # --- ANTEPRIMA SINGOLA ---
        st.subheader("👁️ Anteprima Esempio (Solo 1° file)")
        test_d = Image.open(disegni[0])
        t_name, t_img = list(libreria[scelta].items())[0]
        preview_img = composite_v3_blur(t_img, test_d, t_name)
        if preview_img:
            st.image(preview_img, caption=f"Esempio su {t_name}", width=500)
        
        # --- GENERAZIONE ZIP ---
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            bar = st.progress(0)
            target_tmpls = libreria[scelta]
            total = len(disegni) * len(target_tmpls)
            count = 0
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                for t_name, t_img in target_tmpls.items():
                    res = composite_v3_blur(t_img, d_img, t_name)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zip_file.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    count += 1
                    bar.progress(count / total)
        
        st.success("✅ Generazione completata!")
        st.download_button("📥 SCARICA ZIP COMPLETO", data=zip_buf.getvalue(), file_name=f"Mockups_{scelta}.zip")

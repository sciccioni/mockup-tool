import streamlit as st
import numpy as np
from PIL import Image, ImageFilter
import os
import io
import zipfile

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup - Full Preview", layout="wide")

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

# --- LOGICA CORE CON BLUR 1px ---
def find_book_region(tmpl_gray, bg_val):
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 3)
    rows = np.any(book_mask, axis=1); cols = np.any(book_mask, axis=0)
    if not rows.any() or not cols.any(): return None
    by1, by2 = np.where(rows)[0][[0, -1]]
    bx1, bx2 = np.where(cols)[0][[0, -1]]
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    face_x1 = bx1
    for x in range(bx1, bx2 - 5):
        if np.all(row[x:x + 5] >= 240):
            face_x1 = x; break
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area)) if face_area.size > 0 else 246.0
    return {'bx1': int(bx1), 'bx2': int(bx2), 'by1': int(by1), 'by2': int(by2), 'face_val': face_val}

def composite_v3_full(tmpl_pil, cover_pil, template_name=""):
    # APPLICO SFOCATURA 1PX
    cover_pil = cover_pil.convert('RGB').filter(ImageFilter.GaussianBlur(radius=1))
    
    tmpl = np.array(tmpl_pil).astype(np.float64)
    tmpl_gray = (0.299 * tmpl[:,:,0] + 0.587 * tmpl[:,:,1] + 0.114 * tmpl[:,:,2]) if tmpl.ndim == 3 else tmpl
    h, w = tmpl_gray.shape
    cover = np.array(cover_pil).astype(np.float64)
    
    corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
    bg_val = float(np.median(corners))
    reg = find_book_region(tmpl_gray, bg_val)
    if reg is None: return None
    
    target_w, target_h = reg['bx2'] - reg['bx1'] + 1, reg['by2'] - reg['by1'] + 1
    is_base = any(x in template_name.lower() for x in ["base_copertina", "temi_app"])
    bleed = 15 if is_base else 12
    
    cover_res = np.array(Image.fromarray(cover.astype(np.uint8)).resize((target_w + bleed*2, target_h + bleed*2), Image.LANCZOS)).astype(np.float64)
    cover_final = cover_res[bleed:bleed+target_h, bleed:bleed+target_w]
    
    result = np.stack([tmpl_gray]*3, axis=2)
    book_ratio = np.minimum(tmpl_gray[reg['by1']:reg['by2']+1, reg['bx1']:reg['bx2']+1] / reg['face_val'], 1.0)
    
    for c in range(3):
        result[reg['by1']:reg['by2']+1, reg['bx1']:reg['bx2']+1, c] = cover_final[:, :, c] * book_ratio
            
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

# --- INTERFACCIA ---
st.title("🚀 Mockup Engine - Anteprima Totale")

col1, col2 = st.columns([2, 1])
with col1:
    scelta = st.radio("Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
with col2:
    if st.button("🗑️ Reset"):
        st.session_state.uploader_key += 1
        st.rerun()

disegni = st.file_uploader("Carica i tuoi design", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

if st.button("🔥 GENERA E MOSTRA TUTTO"):
    if not disegni or not libreria[scelta]:
        st.error("Carica i file e controlla la cartella templates!")
    else:
        target_tmpls = libreria[scelta]
        first_d = Image.open(disegni[0])
        
        # --- SEZIONE ANTEPRIME (SOLO IL PRIMO DESIGN SU TUTTI I TEMPLATE) ---
        st.subheader(f"🖼️ Anteprima Design: {disegni[0].name} (Tutti i template {scelta})")
        cols = st.columns(4)
        for idx, (t_name, t_img) in enumerate(target_tmpls.items()):
            prev = composite_v3_full(t_img, first_d, t_name)
            if prev:
                cols[idx % 4].image(prev, caption=t_name, use_column_width=True)

        # --- PROCESSO ZIP (TUTTI I DESIGN) ---
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED) as zip_f:
            progress_bar = st.progress(0)
            total_tasks = len(disegni) * len(target_tmpls)
            done = 0
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                for t_name, t_img in target_tmpls.items():
                    res = composite_v3_full(t_img, d_img, t_name)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zip_f.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    done += 1
                    progress_bar.progress(done / total_tasks)
        
        st.success("Tutti i mockup sono pronti!")
        st.download_button("📥 SCARICA ZIP", zip_buf.getvalue(), f"Mockups_{scelta}.zip", "application/zip")

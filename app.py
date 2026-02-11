import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import io
import zipfile

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup Compositor - V3 Final (Fix Dorso)", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- LOGICA DI SMISTAMENTO ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["20x20", "30x30"]): return "Quadrati"
    return "Altro"

# ===================================================================
# FUNZIONI ORIGINALI V3 FINAL (CON FIX DORSO)
# ===================================================================

def find_book_region(tmpl_gray, bg_val):
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 3)
    rows = np.any(book_mask, axis=1)
    cols = np.any(book_mask, axis=0)
    
    if not rows.any() or not cols.any():
        return None
    
    by1, by2 = np.where(rows)[0][[0, -1]]
    bx1, bx2 = np.where(cols)[0][[0, -1]]
    
    # === FIX DORSO BIANCO ===
    # Spostiamo l'inizio del libro 2 pixel a sinistra per coprire il bordo bianco
    bx1 = max(0, bx1 - 2)
    # ========================
    
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    
    face_x1 = bx1
    window_size = 8
    for x in range(bx1, bx2 - window_size):
        window = row[x:x + window_size]
        if np.all(window >= 244):
            face_x1 = x
            break
            
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area))
    
    return {
        'book_x1': int(bx1), 'book_x2': int(bx2),
        'book_y1': int(by1), 'book_y2': int(by2),
        'face_x1': int(face_x1),
        'spine_w': int(face_x1 - bx1),
        'face_w': int(bx2 - face_x1 + 1),
        'face_h': int(by2 - by1 + 1),
        'face_val': face_val,
    }

def composite_v3(tmpl_pil, cover_pil):
    tmpl = np.array(tmpl_pil).astype(np.float64)
    
    if tmpl.ndim == 3:
        tmpl_gray = (0.299 * tmpl[:,:,0] + 0.587 * tmpl[:,:,1] + 0.114 * tmpl[:,:,2])
    else:
        tmpl_gray = tmpl
        
    h, w = tmpl_gray.shape
    cover = np.array(cover_pil.convert('RGB')).astype(np.float64)
    
    corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
    bg_val = float(np.median(corners))
    
    region = find_book_region(tmpl_gray, bg_val)
    if region is None: return None
    
    bx1, bx2 = region['book_x1'], region['book_x2']
    by1, by2 = region['book_y1'], region['book_y2']
    fx1 = region['face_x1']
    spine_w = region['spine_w']
    face_w, face_h = region['face_w'], region['face_h']
    face_val = region['face_val']
    
    cover_resized = np.array(
        Image.fromarray(cover.astype(np.uint8)).resize((face_w, face_h), Image.LANCZOS)
    ).astype(np.float64)
    
    spine_strip_w = max(1, face_w // 20)
    spine_color = np.median(cover_resized[:, :spine_strip_w].reshape(-1, 3), axis=0)
    
    result = np.stack([tmpl_gray, tmpl_gray, tmpl_gray], axis=2)
    
    face_tmpl = tmpl_gray[by1:by2+1, fx1:bx2+1]
    face_ratio = np.minimum(face_tmpl / face_val, 1.05)
    
    for c in range(3):
        result[by1:by2+1, fx1:bx2+1, c] = cover_resized[:, :, c] * face_ratio
        
    if spine_w > 0:
        spine_tmpl = tmpl_gray[by1:by2+1, bx1:fx1]
        spine_ratio = spine_tmpl / face_val
        for c in range(3):
            result[by1:by2+1, bx1:fx1, c] = spine_color[c] * spine_ratio
            
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- CARICAMENTO AUTOMATICO ---
@st.cache_data
def load_fixed_templates():
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    base_path = "templates"
    if os.path.exists(base_path):
        for f_name in os.listdir(base_path):
            if f_name.lower().endswith(('jpg', 'jpeg', 'png')):
                cat = get_manual_cat(f_name)
                if cat in lib:
                    img = Image.open(os.path.join(base_path, f_name)).convert('RGB')
                    lib[cat][f_name] = img
    return lib

libreria = load_fixed_templates()

# --- INTERFACCIA ---
st.title("📖 PhotoBook Mockup Compositor - V3 Final")

t1, t2, t3 = st.tabs(["Verticali", "Orizzontali", "Quadrati"])
for i, (tab, name) in enumerate(zip([t1, t2, t3], ["Verticali", "Orizzontali", "Quadrati"])):
    with tab:
        items = libreria[name]
        if not items: st.info("Nessun template caricato su GitHub.")
        else:
            cols = st.columns(4)
            for idx, (fname, img) in enumerate(items.items()):
                cols[idx % 4].image(img, caption=fname, use_container_width=True)

st.divider()

st.subheader("⚡ Produzione")
col_sel, col_del = st.columns([3, 1])

with col_sel:
    scelta = st.radio("Seleziona formato grafiche:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)

with col_del:
    if st.button("🧹 SVUOTA DESIGN"):
        st.session_state.uploader_key += 1
        st.rerun()

disegni = st.file_uploader(f"Carica i design {scelta}", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

if st.button("🚀 GENERA MOCKUP"):
    if not disegni or not libreria[scelta]:
        st.error("Carica i design!")
    else:
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
                    res = composite_v3(t_img, d_img)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95, subsampling=0)
                        zip_file.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    count += 1
                    bar.progress(count / total)
        st.success("✅ Elaborazione completata!")
        st.download_button("📥 SCARICA ZIP", data=zip_buf.getvalue(), file_name=f"Mockups_{scelta}_V3.zip")

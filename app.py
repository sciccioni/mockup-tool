import streamlit as st
import numpy as np
from PIL import Image
import os
import io
import zipfile

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup Compositor - FINAL", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- SMISTAMENTO CATEGORIE ---
def get_manual_cat(filename):
    fn = filename.lower()
    if "base_copertina_verticale" in fn: return "Verticali"
    if "base_copertina_orizzontale" in fn: return "Orizzontali"
    if any(x in fn for x in ["15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["20x20", "30x30"]): return "Quadrati"
    return "Altro"

# ===================================================================
# LOGICA ORIGINALE V3 + OVER-BLEEDING FIX
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
    
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    
    face_x1 = bx1
    window_size = 8
    for x in range(bx1, bx2 - window_size):
        if np.all(row[x:x + window_size] >= 244):
            face_x1 = x
            break
            
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area)) if face_area.size > 0 else 246.0
    
    return {
        'book_x1': int(bx1), 'book_x2': int(bx2),
        'book_y1': int(by1), 'book_y2': int(by2),
        'face_x1': int(face_x1),
        'spine_w': int(face_x1 - bx1),
        'face_w': int(bx2 - face_x1 + 1),
        'face_h': int(by2 - by1 + 1),
        'face_val': face_val,
    }

def composite_final(tmpl_pil, cover_pil):
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

    # --- OVER-BLEEDING FIX PER ELIMINARE LINEE BIANCHE ---
    bleed = 3  # pixel extra per l'over-bleeding
    
    # 1. SPINE con over-bleeding
    result = np.stack([tmpl_gray, tmpl_gray, tmpl_gray], axis=2)
    
    if spine_w > 0:
        spine_h = face_h
        # Resize con over-bleeding
        spine_resized_big = np.array(
            Image.fromarray(cover.astype(np.uint8)).resize(
                (spine_w + bleed*2, spine_h + bleed*2), Image.LANCZOS
            )
        ).astype(np.float64)
        # Crop al centro
        spine_resized = spine_resized_big[bleed:bleed+spine_h, bleed:bleed+spine_w]
        
        spine_color = np.median(spine_resized[:, :max(1, spine_w//20)].reshape(-1, 3), axis=0)
        spine_tmpl = tmpl_gray[by1:by2+1, bx1:fx1]
        spine_ratio = np.minimum(spine_tmpl / face_val, 1.0)
        
        for c in range(3):
            result[by1:by2+1, bx1:fx1, c] = spine_color[c] * spine_ratio
    
    # 2. FACE con over-bleeding
    # Resize con over-bleeding
    face_resized_big = np.array(
        Image.fromarray(cover.astype(np.uint8)).resize(
            (face_w + bleed*2, face_h + bleed*2), Image.LANCZOS
        )
    ).astype(np.float64)
    # Crop al centro
    face_resized = face_resized_big[bleed:bleed+face_h, bleed:bleed+face_w]
    
    face_tmpl = tmpl_gray[by1:by2+1, fx1:bx2+1]
    face_ratio = np.minimum(face_tmpl / face_val, 1.0)
    
    for c in range(3):
        result[by1:by2+1, fx1:bx2+1, c] = face_resized[:, :, c] * face_ratio
            
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- CARICAMENTO ---
@st.cache_data
def load_templates():
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    base_path = "templates"
    
    if not os.path.exists(base_path):
        return lib
    
    for f_name in os.listdir(base_path):
        if f_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            cat = get_manual_cat(f_name)
            if cat in lib:
                try:
                    img = Image.open(os.path.join(base_path, f_name)).convert('RGB')
                    lib[cat][f_name] = img
                except:
                    pass
    
    return lib

@st.cache_data
def get_thumbnails():
    lib = load_templates()
    thumbs = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    thumb_size = (300, 300)
    
    for cat in lib:
        for fname, img in lib[cat].items():
            thumb = Image.new('RGB', thumb_size, (240, 240, 240))
            img_aspect = img.width / img.height
            thumb_aspect = thumb_size[0] / thumb_size[1]
            
            if img_aspect > thumb_aspect:
                new_w = thumb_size[0]
                new_h = int(thumb_size[0] / img_aspect)
            else:
                new_h = thumb_size[1]
                new_w = int(thumb_size[1] * img_aspect)
            
            resized = img.resize((new_w, new_h), Image.LANCZOS)
            x = (thumb_size[0] - new_w) // 2
            y = (thumb_size[1] - new_h) // 2
            thumb.paste(resized, (x, y))
            thumbs[cat][fname] = thumb
    
    return lib, thumbs

libreria, thumbnails = get_thumbnails()

# --- INTERFACCIA ---
st.title("📖 PhotoBook Mockup Compositor - FINAL")

if st.button("🔄 RICARICA TEMPLATES"):
    st.cache_data.clear()
    st.rerun()

tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])
for i, (tab, name) in enumerate(zip(tabs, ["Verticali", "Orizzontali", "Quadrati"])):
    with tab:
        items = thumbnails[name]
        if not items:
            st.info("Templates non trovati.")
        else:
            cols = st.columns(4)
            for idx, (fname, thumb) in enumerate(items.items()):
                cols[idx % 4].image(thumb, caption=fname, use_column_width=True)

st.divider()

st.subheader("⚡ Produzione")
col_sel, col_del = st.columns([3, 1])
with col_sel:
    scelta = st.radio("Seleziona formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
with col_del:
    if st.button("🗑️ SVUOTA DESIGN"):
        st.session_state.uploader_key += 1
        st.rerun()

disegni = st.file_uploader(f"Carica design {scelta}", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

if st.button("🚀 GENERA TUTTI"):
    if not disegni or not libreria[scelta]:
        st.error("Mancano i file!")
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
                    res = composite_final(t_img, d_img)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95, subsampling=0)
                        zip_file.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    count += 1
                    bar.progress(count / total)
        st.success("✅ Completato!")
        st.download_button("📥 SCARICA ZIP", data=zip_buf.getvalue(), file_name=f"Mockups_{scelta}.zip")

import streamlit as st
import numpy as np
from PIL import Image
import os
import io
import zipfile

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup Compositor - V3 FIXED", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- SMISTAMENTO CATEGORIE ---
def get_manual_cat(filename):
    fn = filename.lower()
    if "base_copertina_verticale" in fn: return "Verticali"
    if "base_verticale_temi_app" in fn: return "Verticali"
    if "base_bottom_app" in fn: return "Verticali"
    if "base_copertina_orizzontale" in fn: return "Orizzontali"
    if "base_orizzontale_temi_app" in fn: return "Orizzontali"
    if "base_quadrata_temi_app" in fn: return "Quadrati"
    if any(x in fn for x in ["15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["20x20", "30x30"]): return "Quadrati"
    return "Altro"

# ===================================================================
# LOGICA V3 FIXED - ANTI WHITE LINE (OVER-BLEEDING)
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
    window_size = 5
    threshold = 240
    
    for x in range(bx1, bx2 - window_size):
        if np.all(row[x:x + window_size] >= threshold):
            face_x1 = x
            break
            
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area)) if face_area.size > 0 else 246.0
    
    return {
        'book_x1': int(bx1), 'book_x2': int(bx2),
        'book_y1': int(by1), 'book_y2': int(by2),
        'face_x1': int(face_x1),
        'face_w': int(bx2 - face_x1 + 1),
        'face_h': int(by2 - by1 + 1),
        'face_val': face_val,
    }

def composite_v3_fixed(tmpl_pil, cover_pil, template_name=""):
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
    face_val = region['face_val']
    target_w = bx2 - bx1 + 1
    target_h = by2 - by1 + 1
    
    if ("base_copertina" in template_name.lower() or "temi_app" in template_name.lower()):
        real_bx1, real_bx2 = 0, w-1
        for x in range(w):
            if np.any(tmpl_gray[:, x] < 250): {real_bx1 := x}; break
        for x in range(w-1, -1, -1):
            if np.any(tmpl_gray[:, x] < 250): {real_bx2 := x}; break
        
        real_by1, real_by2 = 0, h-1
        for y in range(h):
            if np.any(tmpl_gray[y, :] < 250): {real_by1 := y}; break
        for y in range(h-1, -1, -1):
            if np.any(tmpl_gray[y, :] < 250): {real_by2 := y}; break
        
        real_bx1, real_bx2 = max(0, real_bx1-2), min(w-1, real_bx2+2)
        real_by1, real_by2 = max(0, real_by1-2), min(h-1, real_by2+2)
        real_w, real_h = real_bx2-real_bx1+1, real_by2-real_by1+1
        
        bleed = 15
        cover_big = np.array(Image.fromarray(cover.astype(np.uint8)).resize((real_w + bleed*2, real_h + bleed*2), Image.LANCZOS)).astype(np.float64)
        cover_final = cover_big[bleed:bleed+real_h, bleed:bleed+real_w]
        
        result = np.stack([tmpl_gray, tmpl_gray, tmpl_gray], axis=2)
        book_ratio = np.minimum(tmpl_gray[real_by1:real_by2+1, real_bx1:real_bx2+1] / face_val, 1.0)
        for c in range(3):
            result[real_by1:real_by2+1, real_bx1:real_bx2+1, c] = cover_final[:, :, c] * book_ratio
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

    # LOGICA NORMALE
    border_pixels = np.vstack([cover[:, :5].reshape(-1,3), cover[-5:, :].reshape(-1,3), cover[:5, :].reshape(-1,3), cover[:, -5:].reshape(-1,3)])
    border_color = np.median(border_pixels, axis=0)
    
    bleed = 12
    cover_big = np.array(Image.fromarray(cover.astype(np.uint8)).resize((target_w + bleed*2, target_h + bleed*2), Image.LANCZOS)).astype(np.float64)
    cover_final = cover_big[bleed:bleed+target_h, bleed:bleed+target_w]
    
    result = np.stack([tmpl_gray, tmpl_gray, tmpl_gray], axis=2)
    book_ratio = np.minimum(tmpl_gray[by1:by2+1, bx1:bx2+1] / face_val, 1.0)
    for c in range(3):
        result[by1:by2+1, bx1:bx2+1, c] = cover_final[:, :, c] * book_ratio
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- CARICAMENTO ---
@st.cache_data
def load_fixed_templates():
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    base_path = "templates"
    if not os.path.exists(base_path): return lib
    for f_name in os.listdir(base_path):
        if f_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            cat = get_manual_cat(f_name)
            if cat in lib:
                try:
                    img = Image.open(os.path.join(base_path, f_name)).convert('RGB')
                    lib[cat][f_name] = img
                except: pass
    return lib

@st.cache_data
def get_template_thumbnails():
    lib = load_fixed_templates()
    thumbs = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    tw, th = 300, 300
    for cat in lib:
        for fname, img in lib[cat].items():
            thumb = Image.new('RGB', (tw, th), (240, 240, 240))
            img_asp, thumb_asp = img.width/img.height, tw/th
            nw, nh = (tw, int(tw/img_asp)) if img_asp > thumb_asp else (int(th*img_asp), th)
            resized = img.resize((nw, nh), Image.LANCZOS)
            thumb.paste(resized, ((tw-nw)//2, (th-nh)//2))
            thumbs[cat][fname] = thumb
    return lib, thumbs

libreria, thumbnails = get_template_thumbnails()

# --- INTERFACCIA ---
st.title("📖 PhotoBook Mockup Compositor - V3 Preview")

tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])
for i, (tab, name) in enumerate(zip(tabs, ["Verticali", "Orizzontali", "Quadrati"])):
    with tab:
        items = thumbnails[name]
        if not items: st.info("Templates non trovati.")
        else:
            cols = st.columns(5)
            for idx, (fname, thumb) in enumerate(items.items()):
                cols[idx % 5].image(thumb, caption=fname, use_column_width=True)

st.divider()

st.subheader("⚡ Produzione")
col_sel, col_del = st.columns([3, 1])
with col_sel:
    scelta = st.radio("Seleziona formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
with col_del:
    if st.button("🗑️ SVUOTA"):
        st.session_state.uploader_key += 1
        st.rerun()

disegni = st.file_uploader(f"Carica design {scelta}", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

# --- LOGICA DI GENERAZIONE CON ANTEPRIME ---
if st.button("🚀 GENERA E MOSTRA ANTEPRIME"):
    if not disegni or not libreria[scelta]:
        st.error("Mancano i file!")
    else:
        zip_buf = io.BytesIO()
        preview_list = [] # Lista per salvare le immagini da mostrare
        
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            bar = st.progress(0)
            target_tmpls = libreria[scelta]
            total = len(disegni) * len(target_tmpls)
            count = 0
            
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                
                # Container per ogni design
                st.markdown(f"### Risultati per: `{d_name}`")
                preview_cols = st.columns(4)
                
                for t_name, t_img in target_tmpls.items():
                    res = composite_v3_fixed(t_img, d_img, t_name)
                    if res:
                        # Salvataggio per ZIP
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=90)
                        zip_file.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                        
                        # Mostra Anteprima
                        preview_cols[count % 4].image(res, caption=f"{t_name}", use_column_width=True)
                        
                        count += 1
                        bar.progress(count / total)
        
        st.success(f"✅ Generati {count} mockup!")
        st.download_button("📥 SCARICA TUTTI I MOCKUP (ZIP)", 
                           data=zip_buf.getvalue(), 
                           file_name=f"Mockups_{scelta}.zip",
                           mime="application/zip")

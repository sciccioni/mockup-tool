import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import shutil
import io

# Configurazione Pagina
st.set_page_config(page_title="PhotoBook Mockup Compositor", layout="centered")

def find_book_region(tmpl_gray, bg_val):
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 5)
    rows = np.any(book_mask, axis=1); cols = np.any(book_mask, axis=0)
    if not rows.any() or not cols.any(): return None
    by1, by2 = np.where(rows)[0][[0, -1]]; bx1, bx2 = np.where(cols)[0][[0, -1]]
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    face_x1 = bx1
    for x in range(bx1, bx2 - 8):
        if np.all(row[x:x+8] >= 242): 
            face_x1 = x
            break
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area))
    return {'y1': by1, 'y2': by2, 'x1': bx1, 'x2': bx2, 'fx1': face_x1, 
            'w': int(bx2 - face_x1 + 1), 'h': int(by2 - by1 + 1), 'val': face_val}

def process_image(tmpl_pil, cover_pil):
    tmpl_orig = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w = tmpl_gray.shape
    cover_rgb = cover_pil.convert('RGB')
    
    bg_val = float(np.median([tmpl_gray[5,5], tmpl_gray[5,w-5], tmpl_gray[h-5,5], tmpl_gray[h-5,w-5]]))
    reg = find_book_region(tmpl_gray, bg_val)
    if not reg: return None

    cover_res = np.array(ImageOps.fit(cover_rgb, (reg['w'], reg['h']), Image.LANCZOS)).astype(np.float64)
    spine_color = np.median(cover_res[:, :max(1, reg['w']//40)].reshape(-1, 3), axis=0)
    
    result = tmpl_orig.copy()
    face_area_tmpl = tmpl_gray[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1]
    face_ratio = np.expand_dims(np.minimum(face_area_tmpl / reg['val'], 1.05), axis=2)
    
    spine_area_tmpl = tmpl_gray[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1']]
    spine_ratio = np.expand_dims(spine_area_tmpl / reg['val'], axis=2)

    result[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1, :] = cover_res * face_ratio
    if reg['fx1'] > reg['x1']:
        result[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1'], :] = spine_color * spine_ratio
            
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- INTERFACCIA UTENTE ---
st.title("📖 PhotoBook Mockup Tool")
st.write("Carica i template e i tuoi design per generare i mockup automaticamente.")

col1, col2 = st.columns(2)
with col1:
    uploaded_templates = st.file_uploader("1. Carica Template (Bianchi)", accept_multiple_files=True, type=['jpg', 'jpeg', 'png'])
with col2:
    uploaded_designs = st.file_uploader("2. Carica Design (Copertine)", accept_multiple_files=True, type=['jpg', 'jpeg', 'png'])

if st.button("🚀 Genera Mockup") and uploaded_templates and uploaded_designs:
    zip_buffer = io.BytesIO()
    import zipfile
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        progress_bar = st.progress(0)
        total = len(uploaded_designs) * len(uploaded_templates)
        count = 0
        
        for d_file in uploaded_designs:
            d_img = Image.open(d_file)
            d_name = os.path.splitext(d_file.name)[0]
            
            for t_file in uploaded_templates:
                t_img = Image.open(t_file)
                t_name = os.path.splitext(t_file.name)[0]
                
                res_img = process_image(t_img, d_img)
                if res_img:
                    buf = io.BytesIO()
                    res_img.save(buf, format="JPEG", quality=90)
                    zip_file.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                
                count += 1
                progress_bar.progress(count / total)
    
    st.success("✅ Elaborazione completata!")
    st.download_button(
        label="📥 Scarica lo ZIP con tutti i Mockup",
        data=zip_buffer.getvalue(),
        file_name="MOCKUPS_FINALI.zip",
        mime="application/zip"
    )
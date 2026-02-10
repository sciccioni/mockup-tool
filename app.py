import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import io
import zipfile

# Configurazione Pagina
st.set_page_config(page_title="PhotoBook PRO: Template fissi", layout="wide")

# Inizializzazione della memoria dell'app (Session State)
if 'database_templates' not in st.session_state:
    st.session_state['database_templates'] = {}

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
    cover_rgb = cover_pil.convert('RGB')
    bg_val = float(np.median([tmpl_gray[5,5], tmpl_gray[5,w-5], tmpl_gray[h-5,5], tmpl_gray[h-5,w-5]])) if 'w' in locals() else 127
    h, w = tmpl_gray.shape
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

# --- SIDEBAR: GESTIONE TEMPLATE ---
st.sidebar.header("📁 1. SETUP TEMPLATE (Una Tantum)")
tipo = st.sidebar.selectbox("Seleziona categoria da caricare:", ["Verticali", "Orizzontali", "Quadrati"])
up_tmpls = st.sidebar.file_uploader(f"Carica template {tipo}", accept_multiple_files=True, key="setup_tmpls")

if st.sidebar.button("Salva Template in Memoria"):
    if up_tmpls:
        st.session_state['database_templates'][tipo] = []
        for f in up_tmpls:
            img = Image.open(f).convert('RGB')
            st.session_state['database_templates'][tipo].append({'name': f.name, 'img': img})
        st.sidebar.success(f"Salvati {len(up_tmpls)} template {tipo}")
    else:
        st.sidebar.error("Carica i file prima!")

# Visualizzazione stato memoria
st.sidebar.write("---")
st.sidebar.write("**Template in memoria:**")
for k in st.session_state['database_templates'].keys():
    st.sidebar.write(f"✅ {k}: {len(st.session_state['database_templates'][k])} file")

if st.sidebar.button("Svuota Memoria"):
    st.session_state['database_templates'] = {}
    st.rerun()

# --- AREA DI LAVORO PRINCIPALE ---
st.title("🚀 Generatore Mockup Rapido")

formato_lavoro = st.selectbox("Su quale formato vuoi lavorare adesso?", ["Verticali", "Orizzontali", "Quadrati"])

st.subheader(f"🖼️ Carica i Design per: {formato_lavoro}")
disegni = st.file_uploader("Trascina qui le immagini colorate", accept_multiple_files=True, key="lavoro_disegni")

if st.button("AVVIA GENERAZIONE"):
    if formato_lavoro not in st.session_state['database_templates'] or not st.session_state['database_templates'][formato_lavoro]:
        st.error(f"Non hai caricato i template {formato_lavoro} nella barra a sinistra!")
    elif not disegni:
        st.error("Carica le immagini dei design!")
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            progress_bar = st.progress(0)
            templates_fissi = st.session_state['database_templates'][formato_lavoro]
            
            total = len(disegni) * len(templates_fissi)
            count = 0
            
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                
                for t_data in templates_fissi:
                    res_img = process_image(t_data['img'], d_img)
                    if res_img:
                        img_io = io.BytesIO()
                        res_img.save(img_io, format='JPEG', quality=90)
                        zip_file.writestr(f"{d_name}/{t_data['name']}", img_io.getvalue())
                    
                    count += 1
                    progress_bar.progress(count / total)
            
            st.success(f"Fatto! Generati {count} mockup.")
            st.download_button("📥 SCARICA ZIP", data=zip_buffer.getvalue(), file_name=f"Mockup_{formato_lavoro}.zip")

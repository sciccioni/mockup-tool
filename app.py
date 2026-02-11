import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import io
import zipfile

# --- CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="PhotoBook Mockup PRO", layout="wide", initial_sidebar_state="expanded")

# CSS per rendere l'interfaccia più bella
st.markdown("""
    <style>
    .template-card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 10px;
        background-color: #f9f9f9;
        text-align: center;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #ff4b4b;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# Inizializzazione Memoria (Session State)
if 'database_templates' not in st.session_state:
    st.session_state['database_templates'] = {"Verticali": [], "Orizzontali": [], "Quadrati": []}

# --- FUNZIONI CORE (NON TOCCATE) ---
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

# --- SIDEBAR: GESTIONE VISIVA TEMPLATE ---
with st.sidebar:
    st.title("📂 Libreria Template")
    st.info("Carica i template vuoti qui. Rimarranno salvati finché non chiudi il browser.")
    
    cat = st.selectbox("Seleziona Categoria:", ["Verticali", "Orizzontali", "Quadrati"])
    new_tmpls = st.file_uploader(f"Aggiungi a {cat}", accept_multiple_files=True, key="sidebar_loader")
    
    if st.button("➕ Memorizza Template"):
        if new_tmpls:
            for f in new_tmpls:
                img = Image.open(f).convert('RGB')
                st.session_state['database_templates'][cat].append({'name': f.name, 'img': img})
            st.success(f"Aggiornati {cat}!")
            st.rerun()

    st.divider()
    if st.button("🗑️ Svuota tutta la libreria"):
        st.session_state['database_templates'] = {"Verticali": [], "Orizzontali": [], "Quadrati": []}
        st.rerun()

# --- MAIN PAGE: UX VISIVA ---
st.title("📖 PhotoBook Composer PRO")

# 1. VISUALIZZAZIONE TEMPLATE IN MEMORIA
st.subheader("🖼️ Template attualmente pronti all'uso")
tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])

for i, formato in enumerate(["Verticali", "Orizzontali", "Quadrati"]):
    with tabs[i]:
        lista = st.session_state['database_templates'][formato]
        if not lista:
            st.warning(f"Nessun template {formato} in memoria. Caricali dalla barra laterale.")
        else:
            cols = st.columns(4) # Griglia di anteprime
            for idx, item in enumerate(lista):
                with cols[idx % 4]:
                    st.image(item['img'], caption=item['name'], use_container_width=True) # Mostra anteprima visiva

st.divider()

# 2. CARICAMENTO DESIGN E AZIONE
st.subheader("⚡ Produzione")
scelta_lavoro = st.radio("Su quale formato vuoi lavorare adesso?", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)

disegni = st.file_uploader(f"Trascina qui le copertine per i {scelta_lavoro}", accept_multiple_files=True)

if st.button("🚀 GENERA MOCKUP E SCARICA ZIP"):
    tmpls_fissi = st.session_state['database_templates'][scelta_lavoro]
    
    if not tmpls_fissi:
        st.error(f"Errore: Carica prima i template {scelta_lavoro} nella libreria!")
    elif not disegni:
        st.error("Errore: Carica i design da applicare!")
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            progress = st.progress(0)
            status = st.empty()
            
            total = len(disegni) * len(tmpls_fissi)
            count = 0
            
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                
                for t_data in tmpls_fissi:
                    status.text(f"Lavorando: {d_name} su {t_data['name']}")
                    res = process_image(t_data['img'], d_img)
                    if res:
                        img_io = io.BytesIO()
                        res.save(img_io, format='JPEG', quality=90)
                        zip_file.writestr(f"{d_name}/{t_data['name']}.jpg", img_io.getvalue())
                    
                    count += 1
                    progress.progress(count / total)
            
            st.success(f"✅ Creati {count} mockup!")
            st.download_button("📥 SCARICA TUTTO (.ZIP)", data=zip_buffer.getvalue(), file_name=f"Mockup_{scelta_lavoro}.zip")

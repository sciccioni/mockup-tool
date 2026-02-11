import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import io
import zipfile

# --- 1. CONFIGURAZIONE E MEMORIA ---
st.set_page_config(page_title="PhotoBook PRO", layout="wide")

# Inizializziamo la libreria se non esiste
if 'libreria' not in st.session_state:
    st.session_state['libreria'] = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}

# --- 2. FUNZIONI DI ELABORAZIONE (LOGICA ORIGINALE) ---
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
    return {'y1': by1, 'y2': by2, 'x1': bx1, 'x2': bx2, 'fx1': face_x1, 'w': int(bx2 - face_x1 + 1), 'h': int(by2 - by1 + 1), 'val': face_val}

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

# --- 3. SIDEBAR (CARICAMENTO) ---
with st.sidebar:
    st.header("📂 Gestione Libreria")
    categoria = st.selectbox("Seleziona dove salvare:", ["Verticali", "Orizzontali", "Quadrati"])
    file_caricati = st.file_uploader("Trascina qui i template bianchi", accept_multiple_files=True, key="uploader")
    
    if st.button("📥 SALVA NELLA LIBRERIA"):
        if file_caricati:
            for f in file_caricati:
                # Salviamo l'immagine direttamente nello stato della sessione
                img = Image.open(f).convert('RGB')
                st.session_state['libreria'][categoria][f.name] = img
            st.success(f"Salvato in {categoria}!")
        else:
            st.error("Nessun file selezionato!")

    st.divider()
    if st.button("🗑️ SVUOTA TUTTO"):
        st.session_state['libreria'] = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
        st.rerun()

# --- 4. MAIN PAGE (VISUALIZZAZIONE E PRODUZIONE) ---
st.title("📖 PhotoBook Composer PRO")

# Mostriamo le anteprime per ogni tab
st.subheader("🖼️ Libreria Template (Anteprime)")
t1, t2, t3 = st.tabs(["Verticali", "Orizzontali", "Quadrati"])

def mostra_galleria(cat_name, tab_obj):
    with tab_obj:
        items = st.session_state['libreria'][cat_name]
        if not items:
            st.info(f"La libreria {cat_name} è vuota. Usa la barra a sinistra per caricare i file.")
        else:
            cols = st.columns(4)
            for i, (nome, img) in enumerate(items.items()):
                cols[i % 4].image(img, caption=nome, use_container_width=True)

mostra_galleria("Verticali", t1)
mostra_galleria("Orizzontali", t2)
mostra_galleria("Quadrati", t3)

st.divider()

# Area Produzione
st.subheader("⚡ Produzione Mockup")
scelta = st.radio("Quale formato vuoi generare ora?", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)

disegni = st.file_uploader(f"Trascina qui le grafiche {scelta}", accept_multiple_files=True, key="disegni_prod")

if st.button("🚀 AVVIA GENERAZIONE"):
    tmpls_attivi = st.session_state['libreria'][scelta]
    if not tmpls_attivi or not disegni:
        st.error("Mancano i template o le grafiche! Controlla la libreria.")
    else:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            progress = st.progress(0)
            log = st.empty()
            total = len(disegni) * len(tmpls_attivi)
            count = 0
            
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                for t_name, t_img in tmpls_attivi.items():
                    log.text(f"Processing: {d_name} su {t_name}")
                    res = process_image(t_img, d_img)
                    if res:
                        img_io = io.BytesIO()
                        res.save(img_io, format='JPEG', quality=90)
                        zip_file.writestr(f"{d_name}/{t_name}.jpg", img_io.getvalue())
                    count += 1
                    progress.progress(count / total)
        
        st.success(f"✅ Generati {count} mockup!")
        st.download_button("📥 SCARICA ZIP RISULTATI", data=zip_buf.getvalue(), file_name=f"Mockups_{scelta}.zip")

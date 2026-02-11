import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import io
import zipfile

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Composer PRO", layout="wide")

# Inizializzazione MEMORIA PERSISTENTE
if 'libreria' not in st.session_state:
    st.session_state['libreria'] = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}

def get_exact_orientation(pil_img):
    w, h = pil_img.size
    ratio = w / h
    if ratio < 0.94: return "Verticali"
    if ratio > 1.06: return "Orizzontali"
    return "Quadrati"

# --- LOGICA DI ELABORAZIONE (NON TOCCARE) ---
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

# --- SIDEBAR ---
with st.sidebar:
    st.header("📂 Gestione Template")
    target_cat = st.selectbox("Categoria di destinazione:", ["Verticali", "Orizzontali", "Quadrati"])
    uploaded_files = st.file_uploader("Trascina i template bianchi", accept_multiple_files=True)
    
    if st.button("💾 CARICA NELLA LIBRERIA"):
        if uploaded_files:
            for f in uploaded_files:
                img = Image.open(f).convert('RGB')
                detected = get_exact_orientation(img)
                if detected == target_cat:
                    # Salviamo con il nome file come chiave per evitare duplicati
                    st.session_state['libreria'][target_cat][f.name] = img
                else:
                    st.sidebar.warning(f"Ignorato {f.name} (è un {detected})")
            st.success("Libreria aggiornata!")

    st.divider()
    if st.button("🗑️ SVUOTA TUTTO"):
        st.session_state['libreria'] = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
        st.rerun()

# --- MAIN PAGE ---
st.title("📖 PhotoBook Composer PRO")

# Visualizzazione Galleria Anteprime
st.subheader("🖼️ Template salvati in memoria")
tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])

for i, cat_name in enumerate(["Verticali", "Orizzontali", "Quadrati"]):
    with tabs[i]:
        tmpls_dict = st.session_state['libreria'][cat_name]
        if not tmpls_dict:
            st.info(f"La memoria per i {cat_name} è vuota.")
        else:
            grid = st.columns(4)
            for idx, (name, img) in enumerate(tmpls_dict.items()):
                grid[idx % 4].image(img, caption=name, use_container_width=True)

st.divider()

# Area di Produzione
st.subheader("⚡ Produzione Mockup")
prod_cat = st.radio("Scegli il formato dei design da caricare:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)

designs = st.file_uploader(f"Trascina qui le grafiche {prod_cat}", accept_multiple_files=True)

if st.button("🚀 GENERA TUTTO"):
    active_tmpls = st.session_state['libreria'][prod_cat]
    if not active_tmpls or not designs:
        st.error("Errore: Memoria vuota o nessun design caricato.")
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            progress = st.progress(0)
            status = st.empty()
            total = len(designs) * len(active_tmpls)
            count = 0
            for d_file in designs:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                for t_name, t_img in active_tmpls.items():
                    status.text(f"Lavorando: {d_name} su {t_name}")
                    res = process_image(t_img, d_img)
                    if res:
                        img_io = io.BytesIO()
                        res.save(img_io, format='JPEG', quality=90)
                        zip_file.writestr(f"{d_name}/{t_name}", img_io.getvalue())
                    count += 1
                    progress.progress(count / total)
        
        st.success(f"✅ Creati {count} mockup!")
        st.download_button("📥 SCARICA ZIP", data=zip_buffer.getvalue(), file_name=f"Mockups_{prod_cat}.zip")

import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import io
import zipfile

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="PhotoBook Mockup PRO", layout="wide")

# Inizializzazione Memoria
if 'database_templates' not in st.session_state:
    st.session_state['database_templates'] = {"Verticali": [], "Orizzontali": [], "Quadrati": []}

def get_exact_orientation(pil_img):
    """Rileva l'orientamento con tolleranza ridotta per evitare errori tra Verticali e Quadrati."""
    w, h = pil_img.size
    ratio = w / h
    if ratio < 0.94: return "Verticali"
    if ratio > 1.06: return "Orizzontali"
    return "Quadrati"

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

# --- SIDEBAR ---
with st.sidebar:
    st.header("📂 Caricamento Template")
    target_cat = st.selectbox("Dove vuoi aggiungere i file?", ["Verticali", "Orizzontali", "Quadrati"])
    uploaded_files = st.file_uploader("Trascina qui i template bianchi", accept_multiple_files=True)
    
    if st.button("💾 Memorizza nella categoria giusta"):
        if uploaded_files:
            added = 0
            for f in uploaded_files:
                img = Image.open(f).convert('RGB')
                detected = get_exact_orientation(img)
                
                # FILTRO RIGIDO: Se sto caricando in 'Verticali', scarto i Quadrati rilevati
                if detected == target_cat:
                    st.session_state['database_templates'][target_cat].append({'name': f.name, 'img': img})
                    added += 1
                else:
                    st.warning(f"File saltato: {f.name} sembra un formato {detected}")
            
            if added > 0: st.success(f"Aggiunti {added} template a {target_cat}!")
            st.rerun()

    st.divider()
    if st.button("🗑️ Svuota Tutto"):
        st.session_state['database_templates'] = {"Verticali": [], "Orizzontali": [], "Quadrati": []}
        st.rerun()

# --- MAIN PAGE ---
st.title("📖 PhotoBook Composer PRO")

# Visualizzazione tabellare delle anteprime
st.subheader("🖼️ Libreria Template Attivi")
tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])

for i, cat_name in enumerate(["Verticali", "Orizzontali", "Quadrati"]):
    with tabs[i]:
        tmpls = st.session_state['database_templates'][cat_name]
        if not tmpls:
            st.write("Vuoto. Carica file dalla sidebar.")
        else:
            cols = st.columns(5)
            for idx, t in enumerate(tmpls):
                with cols[idx % 5]:
                    st.image(t['img'], caption=t['name'], use_container_width=True)

st.divider()

# Produzione
st.subheader("⚡ Produzione")
prod_cat = st.radio("Seleziona il formato dei design che stai per caricare:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)

designs = st.file_uploader(f"Carica i design {prod_cat}", accept_multiple_files=True)

if st.button("🚀 GENERA E SCARICA"):
    active_tmpls = st.session_state['database_templates'][prod_cat]
    if not active_tmpls or not designs:
        st.error("Assicurati di avere template in memoria e di aver caricato i design.")
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            progress = st.progress(0)
            total = len(designs) * len(active_tmpls)
            count = 0
            for d_file in designs:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                for t_data in active_tmpls:
                    res = process_image(t_data['img'], d_img)
                    if res:
                        img_io = io.BytesIO()
                        res.save(img_io, format='JPEG', quality=90)
                        zip_file.writestr(f"{d_name}/{t_data['name']}.jpg", img_io.getvalue())
                    count += 1
                    progress.progress(count / total)
        
        st.download_button("📥 SCARICA ZIP", data=zip_buffer.getvalue(), file_name=f"Mockup_{prod_cat}.zip")

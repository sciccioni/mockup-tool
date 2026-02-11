import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import io
import zipfile

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook PRO - Classic Edition", layout="wide")

# Reset per il caricatore di file
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- 2. LOGICA SMISTAMENTO (Basata sulla tua lista esatta) ---
def get_manual_cat(filename):
    fn = filename.lower()
    # Verticali
    if any(x in fn for x in ["15x22", "20x30"]): return "Verticali"
    # Orizzontali
    if any(x in fn for x in ["20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    # Quadrati
    if any(x in fn for x in ["20x20", "30x30"]): return "Quadrati"
    return "Altro"

@st.cache_data
def load_fixed_templates():
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    base_path = os.path.join(os.getcwd(), "templates")
    if os.path.exists(base_path):
        for f_name in os.listdir(base_path):
            if f_name.lower().endswith(('jpg', 'jpeg', 'png')):
                cat = get_manual_cat(f_name)
                if cat in lib:
                    img = Image.open(os.path.join(base_path, f_name)).convert('RGB')
                    lib[cat][f_name] = img
    return lib

libreria = load_fixed_templates()

# --- 3. LOGICA GENERAZIONE "FULL" (Senza bordi o margini) ---
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
        if np.all(row[x:x+8] >= 242): # Rilevamento piega
            face_x1 = x
            break
            
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area))
    
    return {'y1': by1, 'y2': by2, 'x1': bx1, 'x2': bx2, 'fx1': face_x1, 'w': int(bx2 - face_x1 + 1), 'h': int(by2 - by1 + 1), 'val': face_val}

def process_image(tmpl_pil, cover_pil):
    tmpl_orig = np.array(tmpl_pil).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w = tmpl_gray.shape
    bg_val = float(np.median([tmpl_gray[5,5], tmpl_gray[5,w-5], tmpl_gray[h-5,5], tmpl_gray[h-5,w-5]]))
    
    reg = find_book_region(tmpl_gray, bg_val)
    if not reg: return None

    # Applica l'immagine "a pieno" nell'area del libro
    fw, fh = reg['w'], reg['h']
    resized = ImageOps.fit(cover_pil.convert('RGB'), (fw, fh), Image.LANCZOS)
    cover_res = np.array(resized).astype(np.float64)
    
    # Colore dorso preso dal bordo della grafica
    spine_color = np.median(cover_res[:, :max(1, fw//40)].reshape(-1, 3), axis=0)

    # Maschere di luce/ombra
    face_ratio = np.expand_dims(np.minimum(tmpl_gray[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1] / reg['val'], 1.05), axis=2)
    spine_ratio = np.expand_dims(tmpl_gray[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1']] / reg['val'], axis=2)
    
    res = tmpl_orig.copy()
    res[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1, :] = cover_res * face_ratio
    if reg['fx1'] > reg['x1']:
        res[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1'], :] = spine_color * spine_ratio
    
    return Image.fromarray(np.clip(res, 0, 255).astype(np.uint8))

# --- 4. INTERFACCIA ---
st.title("📖 PhotoBook Composer PRO")

if not any(libreria.values()):
    st.error("❌ Carica i file nella cartella 'templates' su GitHub.")
else:
    st.success(f"✅ Libreria pronta ({sum(len(v) for v in libreria.values())} file)")

t1, t2, t3 = st.tabs(["Verticali", "Orizzontali", "Quadrati"])
for i, (tab, name) in enumerate(zip([t1, t2, t3], ["Verticali", "Orizzontali", "Quadrati"])):
    with tab:
        items = libreria[name]
        if not items: st.write("-")
        else:
            cols = st.columns(4)
            for idx, (fname, img) in enumerate(items.items()):
                cols[idx % 4].image(img, caption=fname, use_container_width=True)

st.divider()

st.subheader("⚡ Produzione")
c_radio, c_btn = st.columns([3, 1])
with c_radio:
    scelta = st.radio("Seleziona formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
with c_btn:
    if st.button("🧹 SVUOTA DESIGN"):
        st.session_state.uploader_key += 1
        st.rerun()

disegni = st.file_uploader(f"Carica design {scelta}", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

if st.button("🚀 GENERA MOCKUP"):
    if not disegni or not libreria[scelta]:
        st.error("Dati mancanti!")
    else:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            bar = st.progress(0)
            total = len(disegni) * len(libreria[scelta])
            count = 0
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                for t_name, t_img in libreria[scelta].items():
                    res = process_image(t_img, d_img)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=90)
                        zip_file.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    count += 1
                    bar.progress(count / total)
        st.download_button("📥 SCARICA ZIP", data=zip_buf.getvalue(), file_name=f"Mockups_{scelta}.zip")

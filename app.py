import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import io
import zipfile

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook PRO - AutoLoad", layout="wide")

# Funzione per capire l'orientamento (per i file pre-caricati)
def get_orient(pil_img):
    w, h = pil_img.size
    ratio = w / h
    if ratio < 0.94: return "Verticali"
    if ratio > 1.06: return "Orizzontali"
    return "Quadrati"

# --- LOGICA DI CARICAMENTO AUTOMATICO ---
@st.cache_data # Questo serve a caricare i 8 template solo 1 volta e tenerli in memoria
def load_fixed_templates():
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    base_path = "templates" # La cartella su GitHub
    if os.path.exists(base_path):
        for f_name in os.listdir(base_path):
            if f_name.lower().endswith(('jpg', 'jpeg', 'png')):
                img = Image.open(os.path.join(base_path, f_name)).convert('RGB')
                cat = get_orient(img)
                lib[cat][f_name] = img
    return lib

libreria = load_fixed_templates()

# --- LOGICA GENERAZIONE (CON MARGINE 5%) ---
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
    tmpl_orig = np.array(tmpl_pil).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w = tmpl_gray.shape
    bg_val = float(np.median([tmpl_gray[5,5], tmpl_gray[5,w-5], tmpl_gray[h-5,5], tmpl_gray[h-5,w-5]]))
    reg = find_book_region(tmpl_gray, bg_val)
    if not reg: return None

    # Margine 5%
    p = 0.05
    fw, fh = reg['w'], reg['h']
    pw, ph = int(fw*(1-p*2)), int(fh*(1-p*2))
    
    canvas = Image.new('RGB', (fw, fh), (245, 245, 245))
    resized = ImageOps.fit(cover_pil.convert('RGB'), (pw, ph), Image.LANCZOS)
    canvas.paste(resized, ((fw-pw)//2, (fh-ph)//2))
    
    cover_res = np.array(canvas).astype(np.float64)
    spine_color = np.median(np.array(resized)[:, :max(1, pw//40)].reshape(-1, 3), axis=0)

    face_ratio = np.expand_dims(np.minimum(tmpl_gray[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1] / reg['val'], 1.05), axis=2)
    spine_ratio = np.expand_dims(tmpl_gray[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1']] / reg['val'], axis=2)
    
    res = tmpl_orig.copy()
    res[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1, :] = cover_res * face_ratio
    if reg['fx1'] > reg['x1']:
        res[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1'], :] = spine_color * spine_ratio
    
    return Image.fromarray(np.clip(res, 0, 255).astype(np.uint8))

# --- INTERFACCIA ---
st.title("🚀 PhotoBook Automator (8 Template Fissi)")

if not any(libreria.values()):
    st.error("⚠️ Attenzione: Cartella 'templates' non trovata su GitHub o vuota!")
else:
    st.success(f"✅ Sistema pronto: {sum(len(v) for v in libreria.values())} template caricati automaticamente.")

# Visualizzazione anteprime fisse
tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])
for i, name in enumerate(["Verticali", "Orizzontali", "Quadrati"]):
    with tabs[i]:
        if not libreria[name]: st.write("Nessun template in questa categoria.")
        else:
            cols = st.columns(4)
            for idx, (n_file, img_file) in enumerate(libreria[name].items()):
                cols[idx % 4].image(img_file, caption=n_file, use_container_width=True)

st.divider()

# Produzione
scelta = st.radio("Quale formato stai caricando?", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
disegni = st.file_uploader(f"Trascina qui le grafiche per i {scelta}", accept_multiple_files=True)

if st.button("🔥 GENERA TUTTI I MOCKUP"):
    if not disegni:
        st.error("Carica i design!")
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            bar = st.progress(0)
            target_tmpls = libreria[scelta]
            total = len(disegni) * len(target_tmpls)
            count = 0
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                for t_name, t_img in target_tmpls.items():
                    res = process_image(t_img, d_img)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=90)
                        zip_file.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    count += 1
                    bar.progress(count / total)
        st.success("Completato!")
        st.download_button("📥 SCARICA ZIP", data=zip_buffer.getvalue(), file_name=f"Mockups_{scelta}.zip")

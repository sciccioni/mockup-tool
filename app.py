import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import io
import zipfile

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook PRO - Smart Border", layout="wide")

# --- 2. LOGICA DI SMISTAMENTO MANUALE ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["15x22", "20x30"]): 
        return "Verticali"
    if any(x in fn for x in ["20x15", "27x20", "32x24", "40x30"]): 
        return "Orizzontali"
    if any(x in fn for x in ["20x20", "30x30"]): 
        return "Quadrati"
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

# --- 3. LOGICA GENERAZIONE (SMART MARGIN) ---
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

    # --- NUOVA LOGICA: COLORE SFONDO DINAMICO ---
    cover_rgb = cover_pil.convert('RGB')
    
    # Campiona il colore dai 4 angoli per trovare lo sfondo della grafica
    w_c, h_c = cover_rgb.size
    corners = [
        cover_rgb.getpixel((5, 5)), 
        cover_rgb.getpixel((w_c-5, 5)), 
        cover_rgb.getpixel((5, h_c-5)), 
        cover_rgb.getpixel((w_c-5, h_c-5))
    ]
    bg_color = tuple(np.median(corners, axis=0).astype(int))

    # Margine di sicurezza 4% (leggermente meno del precedente per un look più pieno)
    p = 0.04
    fw, fh = reg['w'], reg['h']
    pw, ph = int(fw*(1-p*2)), int(fh*(1-p*2))
    
    # Crea il canvas con il colore campionato dalla tua immagine
    canvas = Image.new('RGB', (fw, fh), bg_color)
    resized_design = ImageOps.fit(cover_rgb, (pw, ph), Image.LANCZOS)
    canvas.paste(resized_design, ((fw-pw)//2, (fh-ph)//2))
    
    cover_res = np.array(canvas).astype(np.float64)
    spine_color = np.median(np.array(resized_design)[:, :max(1, pw//40)].reshape(-1, 3), axis=0)

    face_ratio = np.expand_dims(np.minimum(tmpl_gray[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1] / reg['val'], 1.05), axis=2)
    spine_ratio = np.expand_dims(tmpl_gray[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1']] / reg['val'], axis=2)
    
    res = tmpl_orig.copy()
    res[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1, :] = cover_res * face_ratio
    if reg['fx1'] > reg['x1']:
        res[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1'], :] = spine_color * spine_ratio
    
    return Image.fromarray(np.clip(res, 0, 255).astype(np.uint8))

# --- 4. INTERFACCIA ---
st.title("📖 PhotoBook Composer PRO (Smart Border)")

if not any(libreria.values()):
    st.error("❌ Nessun template trovato nella cartella 'templates'.")
else:
    st.success(f"✅ Libreria pronta ({sum(len(v) for v in libreria.values())} file)")

tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])
for i, name in enumerate(["Verticali", "Orizzontali", "Quadrati"]):
    with tabs[i]:
        tmpls = libreria[name]
        if not tmpls: st.info("Vuoto")
        else:
            cols = st.columns(4)
            for idx, (fname, img) in enumerate(tmpls.items()):
                cols[idx % 4].image(img, caption=fname, use_container_width=True)

st.divider()
scelta = st.radio("Cosa carichi?", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
disegni = st.file_uploader("Trascina qui i tuoi design", accept_multiple_files=True)

if st.button("🚀 GENERA ZIP"):
    if not disegni or not libreria[scelta]: st.error("Dati mancanti!")
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
                        res_img = res.convert("RGB") if hasattr(res, "convert") else res
                        res.save(buf, format='JPEG', quality=90)
                        zip_file.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    count += 1
                    bar.progress(count / total)
        st.download_button("📥 SCARICA ZIP", data=zip_buffer.getvalue(), file_name=f"Mockups_{scelta}_Smart.zip")

import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import io
import zipfile

# --- 1. CONFIGURAZIONE E RESET ---
st.set_page_config(page_title="PhotoBook PRO - Fix Bordi", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- 2. LOGICA SMISTAMENTO TEMPLATE ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
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

# --- 3. LOGICA GENERAZIONE (CON FIX REFUSI BIANCHI) ---
def find_book_region(tmpl_gray, bg_val):
    h, w = tmpl_gray.shape
    # Soglia leggermente abbassata per catturare meglio i bordi chiari
    book_mask = tmpl_gray > (bg_val + 3) 
    rows = np.any(book_mask, axis=1); cols = np.any(book_mask, axis=0)
    if not rows.any() or not cols.any(): return None
    by1, by2 = np.where(rows)[0][[0, -1]]; bx1, bx2 = np.where(cols)[0][[0, -1]]
    
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    face_x1 = bx1
    for x in range(bx1, bx2 - 8):
        if np.all(row[x:x+8] >= 240): # Soglia rilevamento piega
            face_x1 = x
            break
            
    # Calcolo valore medio per le ombre
    margin = 30
    face_area_safe = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    if face_area_safe.size == 0: face_val = 250.0 # Fallback se l'area è troppo piccola
    else: face_val = float(np.median(face_area_safe))

    # === FIX REFUSI BIANCHI (ABBONDANZA) ===
    # Espandiamo l'area di ritaglio di 1 pixel in alto, basso e a destra
    # per assicurarci di coprire i bordi bianchi del template.
    bleed = 1
    by1_b = max(0, by1 - bleed)       # Espandi in alto
    by2_b = min(h - 1, by2 + bleed)   # Espandi in basso
    bx2_b = min(w - 1, bx2 + bleed)   # Espandi a destra
    # Nota: Non espandiamo 'face_x1' (la piega sinistra) per mantenerla netta.
    
    # Ricalcola dimensioni con l'abbondanza
    new_w = int(bx2_b - face_x1 + 1)
    new_h = int(by2_b - by1_b + 1)

    return {
        'y1': by1_b, 'y2': by2_b,   # Coordinate verticali espanse
        'x1': bx1,                  # Inizio dorso originale
        'x2': bx2_b,                # Fine destra espansa
        'fx1': face_x1,             # Inizio faccia (piega)
        'w': new_w, 'h': new_h,     # Nuove dimensioni
        'val': face_val
    }

def process_image(tmpl_pil, cover_pil):
    tmpl_orig = np.array(tmpl_pil).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w = tmpl_gray.shape
    # Stima robusta dello sfondo
    bg_samples = [tmpl_gray[5,5], tmpl_gray[5,w-5], tmpl_gray[h-5,5], tmpl_gray[h-5,w-5]]
    bg_val = float(np.median(bg_samples))
    
    reg = find_book_region(tmpl_gray, bg_val)
    if not reg: return None

    # Smart Border Logic
    cover_rgb = cover_pil.convert('RGB')
    wc, hc = cover_rgb.size
    corners = [cover_rgb.getpixel((5,5)), cover_rgb.getpixel((wc-5,5)), cover_rgb.getpixel((5,hc-5)), cover_rgb.getpixel((wc-5,hc-5))]
    bg_color = tuple(np.median(corners, axis=0).astype(int))

    p = 0.04 # Margine di sicurezza 4%
    fw, fh = reg['w'], reg['h']
    pw, ph = int(fw*(1-p*2)), int(fh*(1-p*2))
    
    canvas = Image.new('RGB', (fw, fh), bg_color)
    resized = ImageOps.fit(cover_rgb, (pw, ph), Image.LANCZOS)
    canvas.paste(resized, ((fw-pw)//2, (fh-ph)//2))
    
    cover_res = np.array(canvas).astype(np.float64)
    spine_color = np.median(np.array(resized)[:, :max(1, pw//40)].reshape(-1, 3), axis=0)

    # Applicazione con maschere espanse
    face_mask = tmpl_gray[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1]
    face_ratio = np.expand_dims(np.minimum(face_mask / reg['val'], 1.05), axis=2)
    
    spine_mask = tmpl_gray[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1']]
    # Fix per evitare divisioni per zero se il dorso è troppo stretto/scuro
    spine_val = max(reg['val'], 1.0)
    spine_ratio = np.expand_dims(spine_mask / spine_val, axis=2)
    
    res = tmpl_orig.copy()
    # Applica la copertina sull'area espansa
    res[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1, :] = cover_res * face_ratio
    
    # Applica il dorso (se esiste spazio tra inizio libro e inizio faccia)
    if reg['fx1'] > reg['x1']:
        res[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1'], :] = spine_color * spine_ratio
    
    return Image.fromarray(np.clip(res, 0, 255).astype(np.uint8))

# --- 4. INTERFACCIA ---
st.title("📖 PhotoBook Composer PRO")

if not any(libreria.values()):
    st.error("❌ Cartella 'templates' non trovata su GitHub.")
else:
    st.success(f"✅ Sistema pronto. {sum(len(v) for v in libreria.values())} template caricati.")

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
col_radio, col_clear = st.columns([3, 1])
with col_radio:
    scelta = st.radio("Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
with col_clear:
    if st.button("🧹 SVUOTA DESIGN"):
        st.session_state.uploader_key += 1
        st.rerun()

disegni = st.file_uploader(f"Carica design {scelta}", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")

if st.button("🚀 GENERA MOCKUP"):
    if not disegni or not libreria[scelta]:
        st.error("Mancano file!")
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
        st.success("Fatto!")
        st.download_button("📥 SCARICA ZIP", data=zip_buffer.getvalue(), file_name=f"Mockups_{scelta}_Fixed.zip")

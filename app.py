import streamlit as st
import numpy as np
from PIL import Image
import os
import io
import zipfile

# --- 1. CONFIGURAZIONE E COORDINATE FISSE (SOLO PER TEMPLATE APP) ---
st.set_page_config(page_title="PhotoBook Pro - Production Ready", layout="wide")

# Queste coordinate sono bloccate per i tuoi template specifici. 
# Formato: (x_inizio_%, y_inizio_%, larghezza_%, altezza_%)
TEMPLATE_MAPS = {
    "base_verticale_temi_app": (35.1, 10.4, 29.8, 79.2),
    "base_orizzontale_temi_app": (19.4, 9.4, 61.2, 81.2),
    "base_orizzontale_temi_app3": (19.4, 9.4, 61.2, 81.2),
    "base_quadrata_temi_app": (28.2, 10.4, 43.6, 77.4),
    "base_bottom_app": (22.8, 4.4, 54.8, 89.6),
}

# --- 2. LOGICA AUTOMATICA (FALLBACK PER ALTRI TEMPLATE) ---
def find_book_region(tmpl_gray, bg_val):
    """Rilevamento bordi standard per template non-APP."""
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 3)
    rows = np.any(book_mask, axis=1)
    cols = np.any(book_mask, axis=0)
    
    if not rows.any() or not cols.any():
        return None
    
    by1, by2 = np.where(rows)[0][[0, -1]]
    bx1, bx2 = np.where(cols)[0][[0, -1]]
    
    # Trova il punto bianco per la normalizzazione
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    face_x1 = bx1
    for x in range(bx1, bx2 - 5):
        if np.all(row[x:x+5] >= 240):
            face_x1 = x
            break
            
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area)) if face_area.size > 0 else 246.0
    
    return {'bx1': bx1, 'bx2': bx2, 'by1': by1, 'by2': by2, 'face_val': face_val}

# --- 3. MOTORE DI COMPOSIZIONE ---
def process_mockup(tmpl_pil, cover_pil, t_name):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    cover = cover_pil.convert('RGB')

    # CONTROLLO LOGICA: È un template APP?
    app_key = next((k for k in TEMPLATE_MAPS.keys() if k in t_name.lower()), None)

    if app_key:
        # --- LOGICA A: COORDINATE FISSE + SHADOW MAP ---
        px, py, pw, ph = TEMPLATE_MAPS[app_key]
        x1, y1 = int((px * w) / 100), int((py * h) / 100)
        tw, th = int((pw * w) / 100), int((ph * h) / 100)
        
        c_res = np.array(cover.resize((tw, th), Image.LANCZOS)).astype(np.float64)
        
        # Multiply blending: usa l'ombra del libro originale
        book_shadows = tmpl_gray[y1:y1+th, x1:x1+tw]
        shadow_map = np.clip(book_shadows / 255.0, 0, 1.0)
        
        result = tmpl_rgb.copy()
        for c in range(3):
            result[y1:y1+th, x1:x1+tw, c] = c_res[:, :, c] * shadow_map
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

    else:
        # --- LOGICA B: AUTOMATICA (AS IS) ---
        corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
        bg_val = np.median(corners)
        reg = find_book_region(tmpl_gray, bg_val)
        
        if reg is None: return None
        
        tw, th = reg['bx2'] - reg['bx1'] + 1, reg['by2'] - reg['by1'] + 1
        c_res = np.array(cover.resize((tw, th), Image.LANCZOS)).astype(np.float64)
        
        ratio = np.minimum(tmpl_gray[reg['by1']:reg['by2']+1, reg['bx1']:reg['bx2']+1] / reg['face_val'], 1.0)
        
        result = tmpl_rgb.copy()
        for c in range(3):
            result[reg['by1']:reg['by2']+1, reg['bx1']:reg['bx2']+1, c] = c_res[:, :, c] * ratio
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- 4. INTERFACCIA STREAMLIT ---
st.title("📖 PhotoBook Production System")

# Caricamento Template
@st.cache_data
def get_templates():
    path = "templates"
    if not os.path.exists(path): return {}
    return {f: Image.open(os.path.join(path, f)) for f in os.listdir(path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))}

lib = get_templates()

if not lib:
    st.error("❌ Cartella '/templates' non trovata. Carica i mockup lì dentro.")
else:
    with st.sidebar:
        st.header("Setup")
        sel_t = st.selectbox("Seleziona Mockup:", list(lib.keys()))
        is_app_mode = any(k in sel_t.lower() for k in TEMPLATE_MAPS.keys())
        st.write(f"Modalità: {'**COORDINATE FISSE**' if is_app_mode else '**AUTOMATICA**'}")

    files = st.file_uploader("Carica i tuoi design:", accept_multiple_files=True)

    if files:
        if st.button("🚀 GENERA TUTTI"):
            zip_io = io.BytesIO()
            with zipfile.ZipFile(zip_io, "a", zipfile.ZIP_DEFLATED) as zf:
                bar = st.progress(0)
                for i, f in enumerate(files):
                    res = process_mockup(lib[sel_t], Image.open(f), sel_t)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zf.writestr(f"Mockup_{f.name}", buf.getvalue())
                    bar.progress((i + 1) / len(files))
            
            st.success("✅ Finito!")
            st.download_button("📥 Scarica ZIP", zip_io.getvalue(), f"Mockups_{sel_t}.zip")

        # Anteprima dell'ultimo caricato
        st.divider()
        st.subheader("Anteprima Risultato")
        p_res = process_mockup(lib[sel_t], Image.open(files[-1]), sel_t)
        if p_res: st.image(p_res, use_column_width=True)

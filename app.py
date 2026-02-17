import streamlit as st
import numpy as np
from PIL import Image, ImageDraw
import os
import io
import zipfile
import json

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup Compositor - V3 FIXED", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- ANTI-CACHE ---
def get_folder_hash(folder_path):
    if not os.path.exists(folder_path): return 0
    return sum(os.path.getmtime(os.path.join(folder_path, f)) for f in os.listdir(folder_path))

# --- COORDINATE ---
TEMPLATE_MAPS_FILE = "template_coordinates.json"

def load_template_maps():
    default_maps = {
        "base_verticale_temi_app.jpg": {"coords": (34.4, 9.1, 30.6, 80.4), "offset": 1},
        "base_orizzontale_temi_app.jpg": {"coords": (18.9, 9.4, 61.9, 83.0), "offset": 1},
        "base_orizzontale_temi_app3.jpg": {"coords": (18.7, 9.4, 62.2, 82.9), "offset": 1},
        "base_quadrata_temi_app.jpg": {"coords": (27.7, 10.5, 44.7, 79.4), "offset": 1},
        "base_bottom_app.jpg": {"coords": (21.8, 4.7, 57.0, 91.7), "offset": 1},
        "15x22-crea la tua grafica.jpg": {"coords": (33.1, 21.4, 33.9, 57.0), "offset": 2},
        "Fotolibro-Temi-Verticali-temi-3.png": {"coords": (13.6, 4.0, 73.0, 92.0), "offset": 1},
        "base_copertina_verticale.jpg": {"coords": (0, 0, 100, 100), "offset": 0} # Placeholder per auto-detection
    }
    if os.path.exists(TEMPLATE_MAPS_FILE):
        try:
            with open(TEMPLATE_MAPS_FILE, 'r') as f: return json.load(f)
        except: return default_maps
    return default_maps

def save_template_maps(maps):
    with open(TEMPLATE_MAPS_FILE, 'w') as f: json.dump(maps, f, indent=2)

TEMPLATE_MAPS = load_template_maps()

# --- CATEGORIE ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["vertical", "15x22", "20x30", "bottom", "copertina_verticale"]): return "Verticali"
    if any(x in fn for x in ["orizzontal", "20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["quadrat", "20x20", "30x30"]): return "Quadrati"
    return "Altro"

# --- CORE LOGIC ---
def find_book_region(tmpl_gray, bg_val):
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 3)
    rows, cols = np.any(book_mask, axis=1), np.any(book_mask, axis=0)
    if not rows.any() or not cols.any(): return None
    by1, by2 = np.where(rows)[0][[0, -1]]
    bx1, bx2 = np.where(cols)[0][[0, -1]]
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    face_x1 = bx1
    for x in range(bx1, bx2 - 5):
        if np.all(row[x:x+5] >= 240): {face_x1 := x}; break
    return {'book_x1': int(bx1), 'book_x2': int(bx2), 'book_y1': int(by1), 'book_y2': int(by2), 'face_x1': int(face_x1)}

def composite_v3_fixed(tmpl_pil, cover_pil, template_name="", border_offset=None):
    tmpl_rgb = tmpl_pil.convert('RGB')
    tmpl_array = np.array(tmpl_rgb).astype(np.float64)
    h, w = tmpl_rgb.size[1], tmpl_rgb.size[0]
    
    # 1. PRECISION MAPPING
    if template_name in TEMPLATE_MAPS and template_name != "base_copertina_verticale.jpg":
        d = TEMPLATE_MAPS[template_name]
        px, py, pw, ph = d["coords"]
        bo = border_offset if border_offset is not None else d.get("offset", 1)
        x1, y1 = int((px * w) / 100) + bo, int((py * h) / 100) + bo
        tw, th = int((pw * w) / 100) - (bo * 2), int((ph * h) / 100) - (bo * 2)
        
        target_aspect = tw / th
        cw, ch = cover_pil.size
        if cw/ch > target_aspect:
            nw = int(ch * target_aspect)
            crop = ((cw - nw)//2, 0, (cw - nw)//2 + nw, ch)
        else:
            nh = int(cw / target_aspect)
            crop = (0, (ch - nh)//2, cw, (ch - nh)//2 + nh)
        
        c_res = cover_pil.crop(crop).resize((tw, th), Image.LANCZOS)
        
        # Shadow/Multiply logic
        tmpl_l = np.array(tmpl_pil.convert('L')).astype(np.float64)
        shadows = np.clip(tmpl_l[y1:y1+th, x1:x1+tw] / 246.0, 0, 1.0)
        
        c_array = np.array(c_res.convert('RGB')).astype(np.float64)
        for i in range(3): c_array[:,:,i] *= shadows
        
        # Alpha Handling (No black borders)
        final_face = Image.fromarray(c_array.astype(np.uint8))
        if c_res.mode == 'RGBA':
            tmpl_rgb.paste(final_face, (x1, y1), c_res)
        else:
            tmpl_rgb.paste(final_face, (x1, y1))
        return tmpl_rgb

    # 2. AUTO-DETECTION (Per base_copertina_verticale)
    tmpl_gray = np.array(tmpl_pil.convert('L'))
    region = find_book_region(tmpl_gray, np.median([tmpl_gray[0,0], tmpl_gray[0,-1]]))
    if not region: return tmpl_rgb
    
    bx1, bx2, by1, by2 = region['book_x1'], region['book_x2'], region['book_y1'], region['book_y2']
    if "base_copertina" in template_name.lower():
        # Scansione bordi chirurgica per mockup senza dorso
        for x in range(w): 
            if np.any(tmpl_gray[:, x] < 250): {bx1 := x}; break
        for x in range(w-1, -1, -1): 
            if np.any(tmpl_gray[:, x] < 250): {bx2 := x}; break
    
    tw, th = bx2 - bx1 + 1, by2 - by1 + 1
    c_res = cover_pil.resize((tw, th), Image.LANCZOS)
    
    # Render con Multiply
    c_arr = np.array(c_res.convert('RGB')).astype(np.float64)
    sh = np.clip(tmpl_gray[by1:by2+1, bx1:bx2+1] / 246.0, 0, 1.0)
    for i in range(3): c_arr[:,:,i] *= sh
    
    final_face = Image.fromarray(c_arr.astype(np.uint8))
    if c_res.mode == 'RGBA':
        tmpl_rgb.paste(final_face, (bx1, by1), c_res)
    else:
        tmpl_rgb.paste(final_face, (bx1, by1))
    return tmpl_rgb

# --- LIBRERIA ---
@st.cache_data
def get_lib(h):
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}, "Altro": {}}
    if not os.path.exists("templates"): return lib
    for f in os.listdir("templates"):
        if f.lower().endswith(('.jpg', '.png', '.jpeg')):
            lib[get_manual_cat(f)][f] = Image.open(os.path.join("templates", f)).convert('RGB')
    return lib

libreria = get_lib(get_folder_hash("templates"))

# --- INTERFACCIA ---
menu = st.sidebar.radio("Menu", ["📚 Templates", "🎯 Calibrazione", "⚡ Produzione"])

if menu == "📚 Templates":
    st.subheader("📚 Libreria Templates")
    if st.button("🔄 RICARICA"): st.cache_data.clear(); st.rerun()
    ts = st.tabs(list(libreria.keys()))
    for i, c in enumerate(libreria.keys()):
        with ts[i]:
            cols = st.columns(4)
            for idx, (fn, img) in enumerate(libreria[c].items()):
                cols[idx%4].image(img, caption=fn, use_column_width=True)

elif menu == "🎯 Calibrazione":
    cat = st.selectbox("Categoria:", list(libreria.keys()))
    sel = st.selectbox("Template:", list(libreria[cat].keys()))
    if sel:
        t_img = libreria[cat][sel]
        d = TEMPLATE_MAPS.get(sel, {"coords": (20, 10, 60, 80), "offset": 1})
        if 'cal' not in st.session_state or st.session_state.get('cur') != sel:
            st.session_state.cal = d; st.session_state.cur = sel
        
        col1, col2 = st.columns(2)
        st.session_state.cal["coords"] = [
            col1.number_input("X %", 0.0, 100.0, float(st.session_state.cal["coords"][0])),
            col2.number_input("Y %", 0.0, 100.0, float(st.session_state.cal["coords"][1])),
            col1.number_input("W %", 0.0, 100.0, float(st.session_state.cal["coords"][2])),
            col2.number_input("H %", 0.0, 100.0, float(st.session_state.cal["coords"][3]))
        ]
        st.session_state.cal["offset"] = st.slider("Offset", 0, 20, int(st.session_state.cal["offset"]))
        
        # Anteprima rettangolo
        p_img = t_img.copy(); draw = ImageDraw.Draw(p_img); w, h = p_img.size
        c = st.session_state.cal["coords"]
        draw.rectangle([int(c[0]*w/100), int(c[1]*h/100), int((c[0]+c[2])*w/100), int((c[1]+c[3])*h/100)], outline="red", width=5)
        st.image(p_img, use_column_width=True)
        if st.button("💾 SALVA"):
            TEMPLATE_MAPS[sel] = st.session_state.cal; save_template_maps(TEMPLATE_MAPS); st.success("Salvate!")

elif menu == "⚡ Produzione":
    scelta = st.radio("Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
    up = st.file_uploader("Carica design (PNG supportate)", type=['jpg', 'png'], key='preview')
    
    if up and libreria[scelta]:
        d_img = Image.open(up)
        cols = st.columns(4)
        for i, (t_name, t_img) in enumerate(libreria[scelta].items()):
            with cols[i%4]:
                res = composite_v3_fixed(t_img, d_img, t_name)
                st.image(res, caption=t_name, use_column_width=True)

    st.divider()
    batch = st.file_uploader("Batch Produzione", accept_multiple_files=True)
    if st.button("🚀 GENERA TUTTI") and batch and libreria[scelta]:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED) as zf:
            progress = st.progress(0)
            total = len(batch) * len(libreria[scelta])
            count = 0
            for b_file in batch:
                b_img = Image.open(b_file)
                # DETERMINA FORMATO REALE
                is_png = b_img.mode == 'RGBA' or b_file.name.lower().endswith('.png')
                fmt = 'PNG' if is_png else 'JPEG'
                ext = '.png' if is_png else '.jpg'
                
                name_clean = os.path.splitext(b_file.name)[0]
                if name_clean.lower().endswith('.png'): name_clean = name_clean[:-4] # Evita .png.png
                
                for t_name, t_img in libreria[scelta].items():
                    res = composite_v3_fixed(t_img, b_img, t_name)
                    buf = io.BytesIO()
                    res.save(buf, format=fmt, quality=95 if fmt == 'JPEG' else None)
                    zf.writestr(f"{name_clean}/{t_name.split('.')[0]}{ext}", buf.getvalue())
                    count += 1; progress.progress(count/total)
        st.session_state.zip_ready, st.session_state.zip_data = True, zip_buf.getvalue()
        st.success("Mockup generati con successo!")

    if st.session_state.get('zip_ready'):
        st.download_button("📥 SCARICA ZIP", st.session_state.zip_data, f"Mockups_{scelta}.zip", "application/zip")

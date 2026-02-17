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

# --- FIX CACHE: Rileva modifiche ai file (anche con lo stesso nome) ---
def get_folder_hash(folder_path):
    if not os.path.exists(folder_path):
        return 0
    return sum(os.path.getmtime(os.path.join(folder_path, f)) for f in os.listdir(folder_path))

# --- MAPPING COORDINATE ---
TEMPLATE_MAPS_FILE = "template_coordinates.json"

def load_template_maps():
    default_maps = {
        "base_verticale_temi_app.jpg": {"coords": (34.4, 9.1, 30.6, 80.4), "offset": 1},
        "base_orizzontale_temi_app.jpg": {"coords": (18.9, 9.4, 61.9, 83.0), "offset": 1},
        "base_orizzontale_temi_app3.jpg": {"coords": (18.7, 9.4, 62.2, 82.9), "offset": 1},
        "base_quadrata_temi_app.jpg": {"coords": (27.7, 10.5, 44.7, 79.4), "offset": 1},
        "base_bottom_app.jpg": {"coords": (21.8, 4.7, 57.0, 91.7), "offset": 1},
        "15x22-crea la tua grafica.jpg": {"coords": (33.1, 21.4, 33.9, 57.0), "offset": 2},
        "Fotolibro-Temi-Verticali-temi-3.png": {"coords": (13.6, 4.0, 73.0, 92.0), "offset": 1}
    }
    if os.path.exists(TEMPLATE_MAPS_FILE):
        try:
            with open(TEMPLATE_MAPS_FILE, 'r') as f:
                return json.load(f)
        except: return default_maps
    return default_maps

def save_template_maps(maps):
    with open(TEMPLATE_MAPS_FILE, 'w') as f:
        json.dump(maps, f, indent=2)

TEMPLATE_MAPS = load_template_maps()

# --- SMISTAMENTO CATEGORIE ---
def get_manual_cat(filename):
    fn = filename.lower()
    if "base_copertina_verticale" in fn: return "Verticali"
    if any(x in fn for x in ["vertical", "15x22", "20x30", "bottom"]): return "Verticali"
    if any(x in fn for x in ["orizzontal", "20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["quadrat", "20x20", "30x30"]): return "Quadrati"
    return "Altro"

# ===================================================================
# LOGICA CORE TOTALE (NON MANCA NULLA)
# ===================================================================

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
        if np.all(row[x:x + 5] >= 240):
            face_x1 = x
            break
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area)) if face_area.size > 0 else 246.0
    return {'book_x1': int(bx1), 'book_x2': int(bx2), 'book_y1': int(by1), 'book_y2': int(by2), 'face_x1': int(face_x1), 'face_val': face_val}

def composite_v3_fixed(tmpl_pil, cover_pil, template_name="", border_offset=None):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = (0.299 * tmpl_rgb[:,:,0] + 0.587 * tmpl_rgb[:,:,1] + 0.114 * tmpl_rgb[:,:,2])
    h, w = tmpl_gray.shape
    
    # SE NEL JSON (PRECISION)
    if template_name in TEMPLATE_MAPS:
        d = TEMPLATE_MAPS[template_name]
        px, py, pw, ph = d["coords"]
        bo = border_offset if border_offset is not None else d.get("offset", 1)
        x1, y1 = int((px * w) / 100) + bo, int((py * h) / 100) + bo
        tw, th = int((pw * w) / 100) - (bo * 2), int((ph * h) / 100) - (bo * 2)
        
        # Smart Crop
        t_asp = tw / th
        i_w, i_h = cover_pil.size
        i_asp = i_w / i_h
        if i_asp > t_asp:
            nw = int(i_h * t_asp)
            crop = ((i_w - nw)//2, 0, (i_w - nw)//2 + nw, i_h)
        else:
            nh = int(i_w / t_asp)
            crop = (0, (i_h - nh)//2, i_w, (i_h - nh)//2 + nh)
            
        c_res = np.array(cover_pil.crop(crop).resize((tw, th), Image.LANCZOS)).astype(np.float64)
        sh = np.clip(np.array(tmpl_pil.convert('L'))[y1:y1+th, x1:x1+tw] / 255.0, 0, 1.0)
        res = tmpl_rgb.copy()
        for c in range(3): res[y1:y1+th, x1:x1+tw, c] = c_res[:, :, c] * sh
        return Image.fromarray(np.clip(res, 0, 255).astype(np.uint8))

    # LOGICA AUTOMATICA (BASE COPERTINA E ALTRI)
    corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
    bg_val = float(np.median(corners))
    region = find_book_region(tmpl_gray, bg_val)
    if region is None: return None
    
    if "base_copertina" in template_name.lower():
        real_bx1, real_bx2 = 0, w-1
        for x in range(w):
            if np.any(tmpl_gray[:, x] < 250): {real_bx1 := x}; break
        for x in range(w-1, -1, -1):
            if np.any(tmpl_gray[:, x] < 250): {real_bx2 := x}; break
        real_by1, real_by2 = 0, h-1
        for y in range(h):
            if np.any(tmpl_gray[y, :] < 250): {real_by1 := y}; break
        for y in range(h-1, -1, -1):
            if np.any(tmpl_gray[y, :] < 250): {real_by2 := y}; break
        
        real_w, real_h = real_bx2 - real_bx1 + 1, real_by2 - real_by1 + 1
        bleed = 15
        cover_big = np.array(cover_pil.resize((real_w + bleed*2, real_h + bleed*2), Image.LANCZOS)).astype(np.float64)
        cover_final = cover_big[bleed:bleed+real_h, bleed:bleed+real_w]
        res = tmpl_rgb.copy()
        ratio = np.minimum(tmpl_gray[real_by1:real_by2+1, real_bx1:real_bx2+1] / 246.0, 1.0)
        for c in range(3): res[real_by1:real_by2+1, real_bx1:real_bx2+1, c] = cover_final[:, :, c] * ratio
        return Image.fromarray(np.clip(res, 0, 255).astype(np.uint8))

    # LOGICA NORMALE
    bx1, bx2, by1, by2, face_val = region['book_x1'], region['book_x2'], region['book_y1'], region['book_y2'], region['face_val']
    target_w, target_h = bx2 - bx1 + 1, by2 - by1 + 1
    cover_res = np.array(cover_pil.resize((target_w, target_h), Image.LANCZOS)).astype(np.float64)
    res = tmpl_rgb.copy()
    book_ratio = np.minimum(tmpl_gray[by1:by2+1, bx1:bx2+1] / face_val, 1.0)
    for c in range(3): res[by1:by2+1, bx1:bx2+1, c] = cover_res[:, :, c] * book_ratio
    return Image.fromarray(np.clip(res, 0, 255).astype(np.uint8))

# --- CARICAMENTO LIBRERIA ---
@st.cache_data
def get_library(f_hash):
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}, "Altro": {}}
    if not os.path.exists("templates"): return lib
    for f in os.listdir("templates"):
        if f.lower().endswith(('.jpg', '.png', '.jpeg')):
            cat = get_manual_cat(f)
            lib[cat][f] = Image.open(os.path.join("templates", f)).convert('RGB')
    return lib

libreria = get_library(get_folder_hash("templates"))

# --- INTERFACCIA ---
menu = st.sidebar.radio("Menu", ["📚 Templates", "🎯 Calibrazione Coordinate", "⚡ Produzione"])

if menu == "📚 Templates":
    st.subheader("📚 Libreria Templates")
    if st.button("🔄 RICARICA TEMPLATES"):
        st.cache_data.clear()
        st.rerun()
    tabs = st.tabs(list(libreria.keys()))
    for i, cat in enumerate(libreria.keys()):
        with tabs[i]:
            if not libreria[cat]: st.info("Vuoto")
            else:
                cols = st.columns(4)
                for idx, (fn, img) in enumerate(libreria[cat].items()):
                    cols[idx % 4].image(img, caption=fn, use_column_width=True)

elif menu == "🎯 Calibrazione Coordinate":
    st.header("🎯 Calibrazione")
    cat_choice = st.selectbox("Categoria:", list(libreria.keys()))
    selected_t = st.selectbox("Template:", list(libreria[cat_choice].keys()))
    if selected_t:
        t_img = libreria[cat_choice][selected_t]
        d = TEMPLATE_MAPS.get(selected_t, {"coords": (20.0, 10.0, 60.0, 80.0), "offset": 1})
        if 'cal_px' not in st.session_state or st.session_state.get('last_t') != selected_t:
            st.session_state.update({'cal_px': d["coords"][0], 'cal_py': d["coords"][1], 'cal_pw': d["coords"][2], 'cal_ph': d["coords"][3], 'cal_off': d["offset"], 'last_t': selected_t})
        c1, c2 = st.columns(2)
        st.session_state.cal_px = c1.number_input("X %", 0.0, 100.0, st.session_state.cal_px)
        st.session_state.cal_pw = c1.number_input("Width %", 0.1, 100.0, st.session_state.cal_pw)
        st.session_state.cal_py = c2.number_input("Y %", 0.0, 100.0, st.session_state.cal_py)
        st.session_state.cal_ph = c2.number_input("Height %", 0.1, 100.0, st.session_state.cal_ph)
        st.session_state.cal_off = st.slider("Offset", 0, 20, st.session_state.cal_off)
        
        rect_img = t_img.copy()
        draw = ImageDraw.Draw(rect_img)
        w, h = rect_img.size
        draw.rectangle([int(st.session_state.cal_px*w/100), int(st.session_state.cal_py*h/100), int((st.session_state.cal_px+st.session_state.cal_pw)*w/100), int((st.session_state.cal_py+st.session_state.cal_ph)*h/100)], outline="red", width=3)
        st.image(rect_img, use_column_width=True)
        if st.button("💾 SALVA"):
            TEMPLATE_MAPS[selected_t] = {"coords": (st.session_state.cal_px, st.session_state.cal_py, st.session_state.cal_pw, st.session_state.cal_ph), "offset": st.session_state.cal_off}
            save_template_maps(TEMPLATE_MAPS)
            st.success("Salvate!")

elif menu == "⚡ Produzione":
    st.subheader("⚡ Produzione")
    scelta = st.radio("Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
    
    preview_design = st.file_uploader("Carica design per anteprima", type=['jpg', 'png'], key='prev')
    if preview_design and libreria[scelta]:
        # FIX FORMATO: Legge il formato REALE del file caricato
        d_img = Image.open(preview_design)
        real_format = d_img.format if d_img.format else 'PNG'
        
        st.write(f"🔍 Anteprime per categoria {scelta}:")
        cols = st.columns(4)
        for i, (t_name, t_img) in enumerate(libreria[scelta].items()):
            with cols[i % 4]:
                res = composite_v3_fixed(t_img, d_img, t_name)
                if res: st.image(res, caption=t_name, use_column_width=True)

    st.divider()
    disegni = st.file_uploader("Batch Produzione", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")
    if st.button("🚀 GENERA TUTTI") and disegni and libreria[scelta]:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED) as zf:
            bar = st.progress(0)
            total = len(disegni) * len(libreria[scelta])
            count = 0
            for d_file in disegni:
                # Legge il file e ne determina il formato reale
                d_img_batch = Image.open(d_file)
                # Rispetta l'estensione originale del file caricato
                ext_orig = os.path.splitext(d_file.name)[1].lower()
                if not ext_orig: ext_orig = ".png" # fallback
                
                d_name = os.path.splitext(d_file.name)[0]
                for t_name, t_img in libreria[scelta].items():
                    res = composite_v3_fixed(t_img, d_img_batch, t_name)
                    if res:
                        buf = io.BytesIO()
                        # Salva nel formato corretto
                        save_fmt = 'PNG' if ext_orig == '.png' else 'JPEG'
                        res.save(buf, format=save_fmt, quality=95 if save_fmt == 'JPEG' else None)
                        zf.writestr(f"{d_name}/{t_name}{ext_orig}", buf.getvalue())
                    count += 1
                    bar.progress(count / total)
        st.session_state.zip_ready, st.session_state.zip_data = True, zip_buf.getvalue()
        st.success("Mockup pronti!")
    if st.session_state.get('zip_ready'):
        st.download_button("📥 SCARICA ZIP", st.session_state.zip_data, f"Mockups_{scelta}.zip", "application/zip")

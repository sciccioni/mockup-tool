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

# --- 1. LOGICA ANTI-CACHE (SOLUZIONE PER I FILE CON STESSO NOME) ---
def get_folder_hash(folder_path):
    """Calcola un valore basato sulla data di modifica dei file per forzare il refresh"""
    if not os.path.exists(folder_path):
        return 0
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
        "Fotolibro-Temi-Verticali-temi-3.png": {"coords": (13.6, 4.0, 73.0, 92.0), "offset": 1}
    }
    if os.path.exists(TEMPLATE_MAPS_FILE):
        try:
            with open(TEMPLATE_MAPS_FILE, 'r') as f:
                return json.load(f)
        except: return default_maps
    return default_maps

TEMPLATE_MAPS = load_template_maps()

# --- SMISTAMENTO CATEGORIE (FIXED PER NOMI GENERICI) ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["vertical", "15x22", "20x30", "bottom"]): return "Verticali"
    if any(x in fn for x in ["orizzontal", "20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["quadrat", "20x20", "30x30"]): return "Quadrati"
    return "Altro"

# ===================================================================
# LOGICA DI ELABORAZIONE ORIGINALE (NON TOCCATA)
# ===================================================================

def find_book_region(tmpl_gray, bg_val):
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 3)
    rows = np.any(book_mask, axis=1)
    cols = np.any(book_mask, axis=0)
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
    
    if template_name in TEMPLATE_MAPS:
        t_data = TEMPLATE_MAPS[template_name]
        px, py, pw, ph = t_data["coords"]
        bo = border_offset if border_offset is not None else t_data.get("offset", 1)
        x1, y1 = int((px * w) / 100) + bo, int((py * h) / 100) + bo
        tw, th = int((pw * w) / 100) - (bo * 2), int((ph * h) / 100) - (bo * 2)
        
        # Smart Crop
        target_aspect = tw / th
        img_w, img_h = cover_pil.size
        img_aspect = img_w / img_h
        if img_aspect > target_aspect:
            nw = int(img_h * target_aspect)
            crop = ((img_w - nw) // 2, 0, (img_w - nw) // 2 + nw, img_h)
        else:
            nh = int(img_w / target_aspect)
            crop = (0, (img_h - nh) // 2, img_w, (img_h - nh) // 2 + nh)
            
        c_cropped = cover_pil.crop(crop)
        c_res = np.array(c_cropped.resize((tw, th), Image.LANCZOS)).astype(np.float64)
        tmpl_gray_u8 = np.array(tmpl_pil.convert('L')).astype(np.float64)
        sh_map = np.clip(tmpl_gray_u8[y1:y1+th, x1:x1+tw] / 255.0, 0, 1.0)
        
        result = tmpl_rgb.copy()
        for c in range(3):
            result[y1:y1+th, x1:x1+tw, c] = c_res[:, :, c] * sh_map
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))
    return None

# --- CARICAMENTO LIBRERIA (CON HASH PER REFRESH) ---
@st.cache_data
def get_library(folder_hash):
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}, "Altro": {}}
    base_path = "templates"
    if not os.path.exists(base_path): return lib
    for f in os.listdir(base_path):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            cat = get_manual_cat(f)
            try:
                img = Image.open(os.path.join(base_path, f)).convert('RGB')
                lib[cat][f] = img
            except: pass
    return lib

libreria = get_library(get_folder_hash("templates"))

# --- INTERFACCIA ---
st.title("📖 PhotoBook Mockup Compositor - V3 Fixed")

if st.button("🔄 RICARICA TEMPLATES"):
    st.cache_data.clear()
    st.rerun()

# Tab dinamici basati sulle categorie che contengono immagini
categorie_attive = [k for k, v in libreria.items() if len(v) > 0]
if categorie_attive:
    tabs = st.tabs(categorie_attive)
    for i, cat in enumerate(categorie_attive):
        with tabs[i]:
            cols = st.columns(4)
            for idx, (fname, img) in enumerate(libreria[cat].items()):
                cols[idx % 4].image(img, caption=fname, use_column_width=True)

# --- PRODUZIONE ---
st.divider()
if categorie_attive:
    scelta = st.radio("Seleziona formato per produzione:", categorie_attive, horizontal=True)
    preview_design = st.file_uploader("Carica design per anteprima", type=['jpg', 'png'])
    
    if preview_design:
        d_img = Image.open(preview_design)
        cols = st.columns(4)
        for i, (t_name, t_img) in enumerate(libreria[scelta].items()):
            res = composite_v3_fixed(t_img, d_img, t_name)
            if res:
                cols[i % 4].image(res, caption=t_name, use_column_width=True)

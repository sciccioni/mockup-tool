import streamlit as st
import numpy as np
from PIL import Image, ImageDraw
import os
import io
import zipfile
import json
import cv2 # Assicurati che cv2 sia installato per la logica smart

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup Compositor - V3 FIXED", layout="wide")

# Inizializzazione Session State
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- MAPPING COORDINATE PER TEMPLATE APP ---
TEMPLATE_MAPS_FILE = "template_coordinates.json"

def load_template_maps():
    """Carica le coordinate da file JSON o usa quelle di default aggiornate"""
    default_maps = {
        "base_verticale_temi_app.jpg": {
            "coords": (34.4, 9.1, 30.6, 80.4),
            "offset": 1
        },
        "base_orizzontale_temi_app.jpg": {
            "coords": (18.9, 9.4, 61.9, 83.0),
            "offset": 1
        },
        "base_orizzontale_temi_app3.jpg": {
            "coords": (18.7, 9.4, 62.2, 82.9),
            "offset": 1
        },
        "base_quadrata_temi_app.jpg": {
            "coords": (27.7, 10.5, 44.7, 79.4),
            "offset": 1
        },
        "base_bottom_app.jpg": {
            "coords": (21.8, 4.7, 57.0, 91.7),
            "offset": 1
        },
        "15x22-crea la tua grafica.jpg": {
            "coords": (33.1, 21.4, 33.9, 57.0),
            "offset": 2
        }
    }
    
    if os.path.exists(TEMPLATE_MAPS_FILE):
        try:
            with open(TEMPLATE_MAPS_FILE, 'r') as f:
                loaded = json.load(f)
                result = {}
                for k, v in loaded.items():
                    if isinstance(v, list):
                        result[k] = {"coords": tuple(v), "offset": 1}
                    elif isinstance(v, dict):
                        result[k] = {"coords": tuple(v.get("coords", (20, 10, 60, 80))), "offset": v.get("offset", 1)}
                    else:
                        result[k] = {"coords": tuple(v), "offset": 1}
                return result
        except:
            return default_maps
    return default_maps

TEMPLATE_MAPS = load_template_maps()

# --- SMISTAMENTO CATEGORIE ---
def get_manual_cat(filename):
    fn = filename.lower()
    if "base_copertina_verticale" in fn: return "Verticali"
    if "base_verticale_temi_app" in fn: return "Verticali"
    if "base_bottom_app" in fn: return "Verticali"
    if "base_copertina_orizzontale" in fn: return "Orizzontali"
    if "base_orizzontale_temi_app" in fn: return "Orizzontali"
    if "base_quadrata_temi_app" in fn: return "Quadrati"
    if any(x in fn for x in ["15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["20x20", "30x30"]): return "Quadrati"
    return "Altro"

# ===================================================================
# LOGICA V3 FIXED (CON SMART CROP & OPENCV)
# ===================================================================

def find_book_region(tmpl_gray, bg_val):
    """
    Versione PRO: Usa Computer Vision (OpenCV) per trovare i contorni
    """
    if tmpl_gray.dtype != np.uint8:
        img_u8 = np.clip(tmpl_gray, 0, 255).astype(np.uint8)
    else:
        img_u8 = tmpl_gray

    blurred = cv2.GaussianBlur(img_u8, (5, 5), 0)
    v = np.median(img_u8)
    sigma = 0.33
    lower = int(max(0, (1.0 - sigma) * v))
    upper = int(min(255, (1.0 + sigma) * v))
    edges = cv2.Canny(blurred, lower, upper)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    book_rect = None
    
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        x, y, w, h = cv2.boundingRect(c)
        if w < 50 or h < 50:
            continue
        book_rect = (x, y, w, h)
        break
    
    if book_rect is None:
        return None

    bx, by, bw, bh = book_rect
    margin_x = int(bw * 0.2)
    margin_y = int(bh * 0.2)
    face_area = tmpl_gray[by+margin_y : by+bh-margin_y, bx+margin_x : bx+bw-margin_x]
    face_val = float(np.median(face_area)) if face_area.size > 0 else 240.0

    return {
        'book_x1': int(bx), 'book_x2': int(bx + bw),
        'book_y1': int(by), 'book_y2': int(by + bh),
        'face_x1': int(bx),
        'spine_w': 0,
        'face_w': int(bw),
        'face_h': int(bh),
        'face_val': face_val,
    }

def composite_v3_fixed(tmpl_pil, cover_pil, template_name="", border_offset=None):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = (0.299 * tmpl_rgb[:,:,0] + 0.587 * tmpl_rgb[:,:,1] + 0.114 * tmpl_rgb[:,:,2])
    h, w = tmpl_gray.shape
    
    # --- LOGICA PRECISION PER TEMPLATE APP (COORDINATE ESATTE + SMART CROP) ---
    if template_name in TEMPLATE_MAPS:
        template_data = TEMPLATE_MAPS[template_name]
        px, py, pw, ph = template_data["coords"]
        
        if border_offset is None:
            border_offset = template_data.get("offset", 1)
        
        # 1. Calcola l'area di destinazione
        x1 = int((px * w) / 100) + border_offset
        y1 = int((py * h) / 100) + border_offset
        tw = int((pw * w) / 100) - (border_offset * 2)
        th = int((ph * h) / 100) - (border_offset * 2)
        
        # 2. CROP INTELLIGENTE (EVITA STRETCHING)
        target_aspect = tw / th
        img_w, img_h = cover_pil.size
        img_aspect = img_w / img_h
        
        if img_aspect > target_aspect:
            # Immagine troppo larga: taglia i lati
            new_h = img_h
            new_w = int(new_h * target_aspect)
            offset_x = (img_w - new_w) // 2
            crop_box = (offset_x, 0, offset_x + new_w, new_h)
        else:
            # Immagine troppo alta: taglia sopra/sotto
            new_w = img_w
            new_h = int(new_w / target_aspect)
            offset_y = (img_h - new_h) // 2
            crop_box = (0, offset_y, new_w, offset_y + new_h)
            
        cover_cropped = cover_pil.crop(crop_box)
        cover_res = np.array(cover_cropped.resize((tw, th), Image.LANCZOS)).astype(np.float64)
        
        # 3. Applica ombre e fusione
        tmpl_gray_u8 = np.array(tmpl_pil.convert('L')).astype(np.float64)
        book_shadows = tmpl_gray_u8[y1:y1+th, x1:x1+tw]
        shadow_map = np.clip(book_shadows / 255.0, 0, 1.0)
        
        result = tmpl_rgb.copy()
        for c in range(3):
            result[y1:y1+th, x1:x1+tw, c] = cover_res[:, :, c] * shadow_map
            
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

    # --- LOGICA PER ALTRI TEMPLATE (AUTOMATICO) ---
    cover = np.array(cover_pil.convert('RGB')).astype(np.float64)
    
    corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
    bg_val = float(np.median(corners))
    
    region = find_book_region(tmpl_gray, bg_val)
    if region is None: return None
    
    bx1, bx2 = region['book_x1'], region['book_x2']
    by1, by2 = region['book_y1'], region['book_y2']
    face_val = region['face_val']

    target_w = bx2 - bx1 + 1
    target_h = by2 - by1 + 1
    
    # LOGICA SPECIALE PER TEMPLATE BASE
    if "base_copertina" in template_name.lower():
        # (Codice legacy mantenuto per compatibilità)
        real_bx1 = 0
        for x in range(w):
            col = tmpl_gray[:, x]
            if np.any(col < 250):
                real_bx1 = x
                break
        real_bx2 = w - 1
        for x in range(w-1, -1, -1):
            col = tmpl_gray[:, x]
            if np.any(col < 250):
                real_bx2 = x
                break
        real_by1 = 0
        for y in range(h):
            row = tmpl_gray[y, :]
            if np.any(row < 250):
                real_by1 = y
                break
        real_by2 = h - 1
        for y in range(h-1, -1, -1):
            row = tmpl_gray[y, :]
            if np.any(row < 250):
                real_by2 = y
                break
        
        real_bx1 = max(0, real_bx1 - 2)
        real_bx2 = min(w - 1, real_bx2 + 2)
        real_by1 = max(0, real_by1 - 2)
        real_by2 = min(h - 1, real_by2 + 2)
        
        real_w = real_bx2 - real_bx1 + 1
        real_h = real_by2 - real_by1 + 1
        bleed = 15
        
        cover_big = np.array(
            Image.fromarray(cover.astype(np.uint8)).resize(
                (real_w + bleed*2, real_h + bleed*2), Image.LANCZOS
            )
        ).astype(np.float64)
        
        cover_final = cover_big[bleed:bleed+real_h, bleed:bleed+real_w]
        result = np.stack([tmpl_gray, tmpl_gray, tmpl_gray], axis=2)
        book_tmpl = tmpl_gray[real_by1:real_by2+1, real_bx1:real_bx2+1]
        book_ratio = np.minimum(book_tmpl / face_val, 1.0)
        
        for c in range(3):
            result[real_by1:real_by2+1, real_bx1:real_bx2+1, c] = cover_final[:, :, c] * book_ratio
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))
    
    # LOGICA NORMALE
    border_pixels = []
    border_pixels.append(cover[:, :5].reshape(-1, 3))
    border_pixels.append(cover[-5:, :].reshape(-1, 3))
    border_pixels.append(cover[:5, :].reshape(-1, 3))
    border_pixels.append(cover[:, -5:].reshape(-1, 3))
    border_color = np.median(np.vstack(border_pixels), axis=0)
    
    bleed = 12
    cover_big = np.array(
        Image.fromarray(cover.astype(np.uint8)).resize(
            (target_w + bleed*2, target_h + bleed*2), Image.LANCZOS
        )
    ).astype(np.float64)
    cover_final = cover_big[bleed:bleed+target_h, bleed:bleed+target_w]
    
    border_check = 6
    for x in range(min(border_check, target_w)):
        for y in range(target_h):
            if np.mean(cover_final[y, x]) > np.mean(border_color) + 10:
                cover_final[y, x] = border_color
    for y in range(max(0, target_h-border_check), target_h):
        for x in range(target_w):
            if np.mean(cover_final[y, x]) > np.mean(border_color) + 10:
                cover_final[y, x] = border_color
    for y in range(min(border_check, target_h)):
        for x in range(target_w):
            if np.mean(cover_final[y, x]) > np.mean(border_color) + 10:
                cover_final[y, x] = border_color
    for x in range(max(0, target_w-border_check), target_w):
        for y in range(target_h):
            if np.mean(cover_final[y, x]) > np.mean(border_color) + 10:
                cover_final[y, x] = border_color
    
    result = np.stack([tmpl_gray, tmpl_gray, tmpl_gray], axis=2)
    book_tmpl = tmpl_gray[by1:by2+1, bx1:bx2+1]
    book_ratio = np.minimum(book_tmpl / face_val, 1.0)
    
    for c in range(3):
        result[by1:by2+1, bx1:bx2+1, c] = cover_final[:, :, c] * book_ratio
            
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- CARICAMENTO ---
@st.cache_data
def load_fixed_templates():
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    base_path = "templates"
    
    if not os.path.exists(base_path):
        return lib
    
    for f_name in os.listdir(base_path):
        if f_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            cat = get_manual_cat(f_name)
            if cat in lib:
                try:
                    img = Image.open(os.path.join(base_path, f_name)).convert('RGB')
                    lib[cat][f_name] = img
                except:
                    pass
    return lib

libreria = load_fixed_templates()

# --- INTERFACCIA PRINCIPALE (SENZA MENU) ---
st.title("📖 PhotoBook Mockup Compositor")

# Funzione callback per reset quando cambia formato
def on_format_change():
    st.session_state.uploader_key += 1

col_sel, col_del = st.columns([3, 1])

with col_sel:
    # Aggiunto on_change e key per gestire il reset
    scelta = st.radio(
        "Seleziona formato:", 
        ["Verticali", "Orizzontali", "Quadrati"], 
        horizontal=True,
        key="selected_format",
        on_change=on_format_change
    )

with col_del:
    if st.button("🗑️ SVUOTA TUTTO"):
        st.session_state.uploader_key += 1
        st.rerun()

st.divider()

# --- LOGICA PRODUZIONE ---
preview_design = st.file_uploader(
    f"Carica design per anteprima veloce",
    type=['jpg', 'jpeg', 'png'],
    key=f'preview_uploader_{st.session_state.uploader_key}'
)

if preview_design:
    d_img = Image.open(preview_design)
    
    target_tmpls = libreria[scelta]
    
    if not target_tmpls:
        st.warning(f"Nessun template trovato per {scelta}")
    else:
        st.subheader("Anteprima Template")
        cols = st.columns(4)
        for idx, (t_name, t_img) in enumerate(target_tmpls.items()):
            with cols[idx % 4]:
                with st.spinner(f"..."):
                    result = composite_v3_fixed(t_img, d_img, t_name)
                    if result:
                        if t_name in TEMPLATE_MAPS:
                            offset_used = TEMPLATE_MAPS[t_name].get("offset", 1)
                            st.caption(f"🎯 PRECISION ({offset_used}px)")
                        else:
                            st.caption(f"🤖 AUTO")
                        st.image(result, caption=t_name, use_column_width=True)
                    else:
                        st.error(f"Errore")

st.divider()

st.subheader(f"🚀 Generazione Batch ({scelta})")
disegni = st.file_uploader(
    f"Carica tutti i design {scelta}",
    accept_multiple_files=True,
    key=f"batch_uploader_{st.session_state.uploader_key}" # Key dinamica per il reset
)

if st.button("GENERA TUTTI I MOCKUP", type="primary", use_container_width=True):
    if not disegni or not libreria[scelta]:
        st.error("Carica almeno un design e assicurati che ci siano template!")
    else:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            bar = st.progress(0)
            target_tmpls = libreria[scelta]
            total = len(disegni) * len(target_tmpls)
            count = 0
            
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                
                for t_name, t_img in target_tmpls.items():
                    res = composite_v3_fixed(t_img, d_img, t_name)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95, subsampling=0)
                        zip_file.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    count += 1
                    bar.progress(count / total)
        
        st.success("✅ Completato!")
        st.download_button(
            label="📥 SCARICA ZIP COMPLETO", 
            data=zip_buf.getvalue(), 
            file_name=f"Mockups_{scelta}.zip",
            mime="application/zip",
            use_container_width=True
        )

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

# --- MAPPING COORDINATE PER TEMPLATE APP ---
TEMPLATE_MAPS_FILE = "template_coordinates.json"

def load_template_maps():
    """Carica le coordinate da file JSON o usa quelle di default aggiornate"""
    # Coordinate HARDCODED aggiornate dal tuo JSON
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
        },
        "Fotolibro-Temi-Verticali-temi-2.png": {
            "coords": (13.6, 4.0, 73.0, 92.0),
            "offset": 1
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

def save_template_maps(maps):
    """Salva le coordinate nel file JSON"""
    save_data = {}
    for k, v in maps.items():
        save_data[k] = {
            "coords": list(v["coords"]),
            "offset": v["offset"]
        }
    with open(TEMPLATE_MAPS_FILE, 'w') as f:
        json.dump(save_data, f, indent=2)

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
# LOGICA V3 FIXED (CON SMART CROP)
# ===================================================================

def find_book_region(tmpl_gray, bg_val):
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 3)
    rows = np.any(book_mask, axis=1)
    cols = np.any(book_mask, axis=0)
    
    if not rows.any() or not cols.any():
        return None
    
    by1, by2 = np.where(rows)[0][[0, -1]]
    bx1, bx2 = np.where(cols)[0][[0, -1]]
    
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    
    face_x1 = bx1
    window_size = 5
    threshold = 240
    
    for x in range(bx1, bx2 - window_size):
        if np.all(row[x:x + window_size] >= threshold):
            face_x1 = x
            break
            
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area)) if face_area.size > 0 else 246.0
    
    return {
        'book_x1': int(bx1), 'book_x2': int(bx2),
        'book_y1': int(by1), 'book_y2': int(by2),
        'face_x1': int(face_x1),
        'spine_w': int(face_x1 - bx1),
        'face_w': int(bx2 - face_x1 + 1),
        'face_h': int(by2 - by1 + 1),
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

    # --- LOGICA PER ALTRI TEMPLATE (SENZA MAPPA) ---
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
    
    # LOGICA SPECIALE PER TEMPLATE BASE (SENZA DORSO)
    if "base_copertina" in template_name.lower():
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
    
    # LOGICA NORMALE PER ALTRI TEMPLATE
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
    
    threshold = 230
    border_check = 6
    
    for x in range(min(border_check, target_w)):
        for y in range(target_h):
            pixel_brightness = np.mean(cover_final[y, x])
            border_brightness = np.mean(border_color)
            if pixel_brightness > border_brightness + 10:
                cover_final[y, x] = border_color
    
    for y in range(max(0, target_h-border_check), target_h):
        for x in range(target_w):
            pixel_brightness = np.mean(cover_final[y, x])
            border_brightness = np.mean(border_color)
            if pixel_brightness > border_brightness + 10:
                cover_final[y, x] = border_color
    
    for y in range(min(border_check, target_h)):
        for x in range(target_w):
            pixel_brightness = np.mean(cover_final[y, x])
            border_brightness = np.mean(border_color)
            if pixel_brightness > border_brightness + 10:
                cover_final[y, x] = border_color
    
    for x in range(max(0, target_w-border_check), target_w):
        for y in range(target_h):
            pixel_brightness = np.mean(cover_final[y, x])
            border_brightness = np.mean(border_color)
            if pixel_brightness > border_brightness + 10:
                cover_final[y, x] = border_color
    
    result = np.stack([tmpl_gray, tmpl_gray, tmpl_gray], axis=2)
    
    book_tmpl = tmpl_gray[by1:by2+1, bx1:bx2+1]
    book_ratio = np.minimum(book_tmpl / face_val, 1.0)
    
    for c in range(3):
        result[by1:by2+1, bx1:bx2+1, c] = cover_final[:, :, c] * book_ratio
            
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

def apply_test_image_blended(template_img, test_img, px, py, pw, ph, border_offset=1):
    """Applica l'immagine di test sul template con multiply blend E CROP come nel rendering finale"""
    tmpl_rgb = np.array(template_img.convert('RGB')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    
    x1 = int((px * w) / 100) + border_offset
    y1 = int((py * h) / 100) + border_offset
    tw = int((pw * w) / 100) - (border_offset * 2)
    th = int((ph * h) / 100) - (border_offset * 2)
    
    # --- CROP CON PROPORZIONI ---
    test_w, test_h = test_img.size
    target_aspect = tw / th
    test_aspect = test_w / test_h
    
    if test_aspect > target_aspect:
        new_h = test_h
        new_w = int(test_h * target_aspect)
        crop_x = (test_w - new_w) // 2
        crop_y = 0
    else:
        new_w = test_w
        new_h = int(test_w / target_aspect)
        crop_x = 0
        crop_y = (test_h - new_h) // 2
    
    test_cropped = test_img.crop((crop_x, crop_y, crop_x + new_w, crop_y + new_h))
    test_resized = np.array(test_cropped.resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    tmpl_gray_u8 = np.array(template_img.convert('L')).astype(np.float64)
    book_shadows = tmpl_gray_u8[y1:y1+th, x1:x1+tw]
    shadow_map = np.clip(book_shadows / 255.0, 0, 1.0)
    
    result = tmpl_rgb.copy()
    for c in range(3):
        result[y1:y1+th, x1:x1+tw, c] = test_resized[:, :, c] * shadow_map
    
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

def draw_rectangle_on_template(template_img, px, py, pw, ph):
    """Disegna un rettangolo rosso sull'immagine per mostrare l'area"""
    img = template_img.copy()
    draw = ImageDraw.Draw(img)
    
    w, h = img.size
    x1 = int((px * w) / 100)
    y1 = int((py * h) / 100)
    x2 = x1 + int((pw * w) / 100)
    y2 = y1 + int((ph * h) / 100)
    
    # Rettangolo rosso
    draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=2)
    
    return img

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

@st.cache_data
def get_template_thumbnails():
    lib = load_fixed_templates()
    thumbs = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    thumb_width, thumb_height = 300, 300
    
    for cat in lib:
        for fname, img in lib[cat].items():
            thumb = Image.new('RGB', (thumb_width, thumb_height), (240, 240, 240))
            img_aspect = img.width / img.height
            thumb_aspect = thumb_width / thumb_height
            
            if img_aspect > thumb_aspect:
                new_width = thumb_width
                new_height = int(thumb_width / img_aspect)
            else:
                new_height = thumb_height
                new_width = int(thumb_height * img_aspect)
            
            resized = img.resize((new_width, new_height), Image.LANCZOS)
            x, y = (thumb_width - new_width) // 2, (thumb_height - new_height) // 2
            thumb.paste(resized, (x, y))
            thumbs[cat][fname] = thumb
    return lib, thumbs

def get_all_template_names():
    """Ottiene tutti i nomi dei template dalla cartella templates"""
    base_path = "templates"
    all_templates = []
    
    if os.path.exists(base_path):
        for f_name in os.listdir(base_path):
            if f_name.lower().endswith(('.jpg', '.jpeg', '.png')):
                all_templates.append(f_name)
    
    return sorted(all_templates)

libreria, thumbnails = get_template_thumbnails()

# --- INTERFACCIA ---
st.title("📖 PhotoBook Mockup Compositor - V3 Fixed")

# --- MENU PRINCIPALE ---
menu = st.sidebar.radio("Menu", ["📚 Templates", "🎯 Calibrazione Coordinate", "⚡ Produzione"])

if menu == "📚 Templates":
    if st.button("🔄 RICARICA TEMPLATES"):
        st.cache_data.clear()
        st.rerun()

    tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])
    for i, (tab, name) in enumerate(zip(tabs, ["Verticali", "Orizzontali", "Quadrati"])):
        with tab:
            items = thumbnails[name]
            if not items: 
                st.info("Templates non trovati.")
            else:
                cols = st.columns(4)
                for idx, (fname, thumb) in enumerate(items.items()):
                    cols[idx % 4].image(thumb, caption=fname, use_column_width=True)

elif menu == "🎯 Calibrazione Coordinate":
    st.header("🎯 Calibrazione Coordinate Template")
    
    st.info("💡 Le coordinate vengono salvate nel file template_coordinates.json")
    
    all_template_names = get_all_template_names()
    
    if not all_template_names:
        st.error("Nessun template trovato nella cartella 'templates'!")
    else:
        templates_by_cat = {"Verticali": [], "Orizzontali": [], "Quadrati": [], "Altro": []}
        for tname in all_template_names:
            cat = get_manual_cat(tname)
            templates_by_cat[cat].append(tname)
        
        cat_choice = st.selectbox("Seleziona categoria:", ["Verticali", "Orizzontali", "Quadrati", "Altro"])
        
        if templates_by_cat[cat_choice]:
            selected_template = st.selectbox("Seleziona template:", templates_by_cat[cat_choice])
            
            if selected_template:
                if cat_choice in libreria and selected_template in libreria[cat_choice]:
                    template_img = libreria[cat_choice][selected_template]
                else:
                    template_img = Image.open(os.path.join("templates", selected_template)).convert('RGB')
                
                if selected_template in TEMPLATE_MAPS:
                    template_data = TEMPLATE_MAPS[selected_template]
                    px, py, pw, ph = template_data["coords"]
                    saved_offset = template_data.get("offset", 1)
                    st.success(f"✅ Template calibrato - PRECISION | Offset: {saved_offset}px")
                else:
                    px, py, pw, ph = 20.0, 10.0, 60.0, 80.0
                    saved_offset = 1
                    st.warning(f"⚠️ Template NON calibrato")
                
                st.subheader("Coordinate Salvate")
                col1, col2, col3, col4, col5 = st.columns(5)
                with col1:
                    st.metric("X (%)", f"{px:.1f}")
                with col2:
                    st.metric("Y (%)", f"{py:.1f}")
                with col3:
                    st.metric("Width (%)", f"{pw:.1f}")
                with col4:
                    st.metric("Height (%)", f"{ph:.1f}")
                with col5:
                    st.metric("Offset (px)", f"{saved_offset}")
                
                st.divider()
                
                # Initialize session state
                if 'cal_px' not in st.session_state or st.session_state.get('current_template') != selected_template:
                    st.session_state.cal_px = px
                    st.session_state.cal_py = py
                    st.session_state.cal_pw = pw
                    st.session_state.cal_ph = ph
                    st.session_state.cal_offset = saved_offset
                    st.session_state.test_image = None
                    st.session_state.current_template = selected_template
                
                # Controlli principali
                st.subheader("Controlli")
                
                col1, col2 = st.columns(2)
                with col1:
                    new_px = st.number_input("X Position (%)", 0.0, 100.0, st.session_state.cal_px, 0.1, format="%.1f")
                    new_pw = st.number_input("Width (%)", 1.0, 100.0, st.session_state.cal_pw, 0.1, format="%.1f")
                with col2:
                    new_py = st.number_input("Y Position (%)", 0.0, 100.0, st.session_state.cal_py, 0.1, format="%.1f")
                    new_ph = st.number_input("Height (%)", 1.0, 100.0, st.session_state.cal_ph, 0.1, format="%.1f")
                
                new_offset = st.slider("Border Offset (px)", 0, 20, st.session_state.cal_offset, 1)
                
                st.session_state.cal_px = new_px
                st.session_state.cal_py = new_py
                st.session_state.cal_pw = new_pw
                st.session_state.cal_ph = new_ph
                st.session_state.cal_offset = new_offset
                
                st.divider()
                
                # Tabs per visualizzazione
                tab1, tab2, tab3 = st.tabs(["📏 Rettangolo Rosso", "📸 Immagine di Test", "💾 Salva"])
                
                with tab1:
                    st.write("Visualizza l'area con un rettangolo rosso")
                    rect_img = draw_rectangle_on_template(
                        template_img,
                        st.session_state.cal_px,
                        st.session_state.cal_py,
                        st.session_state.cal_pw,
                        st.session_state.cal_ph
                    )
                    st.image(rect_img, use_column_width=True)
                
                with tab2:
                    test_upload = st.file_uploader("Carica immagine di test", type=['jpg', 'jpeg', 'png'], key='test_img')
                    if test_upload:
                        st.session_state.test_image = Image.open(test_upload)
                    
                    if st.session_state.test_image is not None:
                        preview_img = apply_test_image_blended(
                            template_img,
                            st.session_state.test_image,
                            st.session_state.cal_px,
                            st.session_state.cal_py,
                            st.session_state.cal_pw,
                            st.session_state.cal_ph,
                            st.session_state.cal_offset
                        )
                        st.image(preview_img, caption=f"Anteprima con Offset {st.session_state.cal_offset}px", use_column_width=True)
                    else:
                        st.info("Carica un'immagine di test per vedere l'anteprima")
                
                with tab3:
                    col_save, col_download = st.columns(2)
                    
                    with col_save:
                        if st.button("💾 SALVA COORDINATE", type="primary", use_container_width=True):
                            TEMPLATE_MAPS[selected_template] = {
                                "coords": (st.session_state.cal_px, st.session_state.cal_py,
                                           st.session_state.cal_pw, st.session_state.cal_ph),
                                "offset": st.session_state.cal_offset
                            }
                            save_template_maps(TEMPLATE_MAPS)
                            st.success("✅ Coordinate salvate!")
                            st.balloons()
                    
                    with col_download:
                        json_data = json.dumps(TEMPLATE_MAPS, indent=2)
                        st.download_button(
                            label="📥 SCARICA JSON",
                            data=json_data,
                            file_name="template_coordinates.json",
                            mime="application/json",
                            use_container_width=True
                        )
                    
                    if selected_template in TEMPLATE_MAPS:
                        if st.button("🗑️ RIMUOVI CALIBRAZIONE", use_container_width=True):
                            del TEMPLATE_MAPS[selected_template]
                            save_template_maps(TEMPLATE_MAPS)
                            st.success("✅ Calibrazione rimossa!")
                            st.rerun()
        else:
            st.info(f"Nessun template in {cat_choice}")

elif menu == "⚡ Produzione":
    st.subheader("⚡ Produzione")
    
    col_sel, col_del = st.columns([3, 1])
    with col_sel:
        scelta = st.radio("Seleziona formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
    with col_del:
        if st.button("🗑️ SVUOTA"):
            st.session_state.uploader_key += 1
            st.rerun()

    st.subheader(f"🔍 Anteprima {scelta}")
    preview_design = st.file_uploader(
        f"Carica design per anteprima",
        type=['jpg', 'jpeg', 'png'],
        key='preview_uploader'
    )

    if preview_design:
        d_img = Image.open(preview_design)
        st.info(f"Design: {preview_design.name}")
        
        target_tmpls = libreria[scelta]
        
        if not target_tmpls:
            st.warning(f"Nessun template {scelta}")
        else:
            cols = st.columns(4)
            for idx, (t_name, t_img) in enumerate(target_tmpls.items()):
                with cols[idx % 4]:
                    with st.spinner(f"Generando {t_name}..."):
                        result = composite_v3_fixed(t_img, d_img, t_name)
                        if result:
                            if t_name in TEMPLATE_MAPS:
                                offset_used = TEMPLATE_MAPS[t_name].get("offset", 1)
                                st.caption(f"🎯 PRECISION ({offset_used}px)")
                            st.image(result, caption=t_name, use_column_width=True)
                        else:
                            st.error(f"Errore: {t_name}")
        
        st.divider()

    disegni = st.file_uploader(
        f"Carica design {scelta} per batch",
        accept_multiple_files=True,
        key=f"up_{st.session_state.uploader_key}"
    )

    # Bottone per avviare la generazione
    if st.button("🚀 GENERA TUTTI", type="primary"):
        if not disegni or not libreria[scelta]:
            st.error("Mancano i file!")
        else:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                bar = st.progress(0)
                target_tmpls = libreria[scelta]
                total = len(disegni) * len(target_tmpls)
                count = 0
                
                for d_file in disegni:
                    # Reset pointer for multiple reads if needed, though here we open new image
                    d_file.seek(0) 
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
            
            # SALVARE IL RISULTATO IN SESSION_STATE
            st.session_state['zip_ready'] = True
            st.session_state['zip_data'] = zip_buf.getvalue()
            st.session_state['zip_name'] = f"Mockups_{scelta}.zip"
            st.success("✅ Completato! Ora puoi scaricare.")

    # MOSTRARE IL PULSANTE DI DOWNLOAD FUORI DAL BLOCCO DEL BOTTONE DI GENERAZIONE
    if st.session_state.get('zip_ready', False):
        st.download_button(
            label="📥 SCARICA ZIP",
            data=st.session_state['zip_data'],
            file_name=st.session_state['zip_name'],
            mime="application/zip",
            key="download_btn"
        )

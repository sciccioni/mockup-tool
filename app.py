import streamlit as st
import numpy as np
from PIL import Image
import os
import io
import zipfile

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup Compositor - V3 FIXED", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- MAPPING COORDINATE PER TEMPLATE APP ---
TEMPLATE_MAPS = {
    "base_verticale_temi_app.jpg": (35.1, 10.4, 29.8, 79.2),
    "base_orizzontale_temi_app.jpg": (19.4, 9.4, 61.2, 81.2),
    "base_orizzontale_temi_app3.jpg": (19.4, 9.4, 61.2, 81.2),
    "base_quadrata_temi_app.jpg": (28.2, 10.4, 43.6, 77.4),
    "base_bottom_app.jpg": (22.8, 4.4, 54.8, 89.6),
}

# --- SMISTAMENTO CATEGORIE ---
def get_manual_cat(filename):
    fn = filename.lower()
    # Template base piatti
    if "base_copertina_verticale" in fn: return "Verticali"
    if "base_verticale_temi_app" in fn: return "Verticali"
    if "base_bottom_app" in fn: return "Verticali"
    if "base_copertina_orizzontale" in fn: return "Orizzontali"
    if "base_orizzontale_temi_app" in fn: return "Orizzontali"
    if "base_quadrata_temi_app" in fn: return "Quadrati"
    # Template specifici per dimensione
    if any(x in fn for x in ["15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["20x20", "30x30"]): return "Quadrati"
    return "Altro"

# ===================================================================
# LOGICA V3 FIXED
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

def composite_v3_fixed(tmpl_pil, cover_pil, template_name=""):
    # Carichiamo tutto in RGB
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = (0.299 * tmpl_rgb[:,:,0] + 0.587 * tmpl_rgb[:,:,1] + 0.114 * tmpl_rgb[:,:,2])
    h, w = tmpl_gray.shape
    cover = np.array(cover_pil.convert('RGB')).astype(np.float64)
    
    # --- LOGICA PRECISION PER TEMPLATE APP (COORDINATE ESATTE) ---
    if template_name in TEMPLATE_MAPS:
        px, py, pw, ph = TEMPLATE_MAPS[template_name]
        x1, y1 = int((px * w) / 100), int((py * h) / 100)
        tw, th = int((pw * w) / 100), int((ph * h) / 100)
        
        # Resize della cover
        cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
        
        # Shadow Map (Multiply blend mode) - USA GRAYSCALE A 8-BIT
        tmpl_gray_u8 = np.array(tmpl_pil.convert('L')).astype(np.float64)
        book_shadows = tmpl_gray_u8[y1:y1+th, x1:x1+tw]
        shadow_map = np.clip(book_shadows / 255.0, 0, 1.0)  # DIVISO 255 NON 250!
        
        # Composizione
        result = tmpl_rgb.copy()
        for c in range(3):
            result[y1:y1+th, x1:x1+tw, c] = cover_res[:, :, c] * shadow_map
            
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

    # --- LOGICA PER ALTRI TEMPLATE ---
    corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
    bg_val = float(np.median(corners))
    
    region = find_book_region(tmpl_gray, bg_val)
    if region is None: return None
    
    bx1, bx2 = region['book_x1'], region['book_x2']
    by1, by2 = region['book_y1'], region['book_y2']
    face_val = region['face_val']

    target_w = bx2 - bx1 + 1
    target_h = by2 - by1 + 1
    
    # --- LOGICA SPECIALE PER TEMPLATE BASE (SENZA DORSO) ---
    if "base_copertina" in template_name.lower():
        # Template base: rilevamento manuale dei bordi
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
    
    # --- LOGICA NORMALE PER ALTRI TEMPLATE ---
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

libreria, thumbnails = get_template_thumbnails()

# --- INTERFACCIA ---
st.title("📖 PhotoBook Mockup Compositor - V3 Fixed (No White Lines)")

if st.button("🔄 RICARICA TEMPLATES"):
    st.cache_data.clear()
    st.rerun()

tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])
for i, (tab, name) in enumerate(zip(tabs, ["Verticali", "Orizzontali", "Quadrati"])):
    with tab:
        items = thumbnails[name]
        if not items: st.info("Templates non trovati.")
        else:
            cols = st.columns(4)
            for idx, (fname, thumb) in enumerate(items.items()):
                cols[idx % 4].image(thumb, caption=fname, use_column_width=True)

st.divider()

# --- SEZIONE PRODUZIONE ---
st.subheader("⚡ Produzione")
col_sel, col_del = st.columns([3, 1])
with col_sel:
    scelta = st.radio("Seleziona formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
with col_del:
    if st.button("🗑️ SVUOTA DESIGN"):
        st.session_state.uploader_key += 1
        st.rerun()

# --- ANTEPRIMA PER IL FORMATO SELEZIONATO ---
st.subheader(f"🔍 Anteprima Design per formato {scelta}")
preview_design = st.file_uploader(
    f"Carica un design per vedere l'anteprima su tutti i template {scelta}", 
    type=['jpg', 'jpeg', 'png'],
    key='preview_uploader'
)

if preview_design:
    d_img = Image.open(preview_design)
    st.info(f"Design caricato: {preview_design.name}")
    
    target_tmpls = libreria[scelta]
    
    if not target_tmpls:
        st.warning(f"Nessun template {scelta} disponibile.")
    else:
        cols = st.columns(4)
        for idx, (t_name, t_img) in enumerate(target_tmpls.items()):
            with cols[idx % 4]:
                with st.spinner(f"Generando {t_name}..."):
                    result = composite_v3_fixed(t_img, d_img, t_name)
                    if result:
                        st.image(result, caption=t_name, use_column_width=True)
                    else:
                        st.error(f"Errore: {t_name}")
    
    st.divider()

# --- CARICAMENTO MULTIPLO PER PRODUZIONE ---
disegni = st.file_uploader(
    f"Carica design {scelta} per produzione batch", 
    accept_multiple_files=True, 
    key=f"up_{st.session_state.uploader_key}"
)

if st.button("🚀 GENERA TUTTI"):
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
        st.download_button("📥 SCARICA ZIP", data=zip_buf.getvalue(), file_name=f"Mockups_{scelta}.zip")

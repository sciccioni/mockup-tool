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

# --- SMISTAMENTO CATEGORIE ---
def get_manual_cat(filename):
    fn = filename.lower()
    # Template base (con o senza prefisso numerico)
    if "base_copertina_verticale" in fn: return "Verticali"
    if "base_copertina_orizzontale" in fn: return "Orizzontali"
    # Template specifici per dimensione
    if any(x in fn for x in ["15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["20x20", "30x30"]): return "Quadrati"
    return "Altro"

# ===================================================================
# LOGICA V3 FIXED - OVERLAP AUMENTATO A 3 PIXEL
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
    
    # Cerchiamo il punto dove inizia la zona bianca (potenziale face)
    # Ma saremo più conservativi per evitare gap
    face_x1 = bx1
    window_size = 5  # Ridotto da 8 a 5 per essere più sensibili
    threshold = 240  # Ridotto da 244 per catturare meglio il confine
    
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

def composite_v3_fixed(tmpl_pil, cover_pil):
    tmpl = np.array(tmpl_pil).astype(np.float64)
    
    if tmpl.ndim == 3:
        tmpl_gray = (0.299 * tmpl[:,:,0] + 0.587 * tmpl[:,:,1] + 0.114 * tmpl[:,:,2])
    else:
        tmpl_gray = tmpl
        
    h, w = tmpl_gray.shape
    cover = np.array(cover_pil.convert('RGB')).astype(np.float64)
    
    corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
    bg_val = float(np.median(corners))
    
    region = find_book_region(tmpl_gray, bg_val)
    if region is None: return None
    
    bx1, bx2 = region['book_x1'], region['book_x2']
    by1, by2 = region['book_y1'], region['book_y2']
    face_val = region['face_val']
    
    # --- FIX LINEE BIANCHE CON OVER-BLEEDING ---
    target_w = bx2 - bx1 + 1
    target_h = by2 - by1 + 1
    
    # Over-bleeding: scaliamo leggermente più grande (2px) e poi croppiamo al centro
    # Questo assicura che i pixel ai bordi siano pieni e non interpolati con il bianco
    bleed = 2
    cover_resized = np.array(
        Image.fromarray(cover.astype(np.uint8)).resize((target_w + (bleed*2), target_h + (bleed*2)), Image.LANCZOS)
    ).astype(np.float64)
    
    cover_final = cover_resized[bleed:bleed+target_h, bleed:bleed+target_w]
    
    result = np.stack([tmpl_gray, tmpl_gray, tmpl_gray], axis=2)
    
    # Maschera di luminosità dal template
    book_tmpl = tmpl_gray[by1:by2+1, bx1:bx2+1]
    
    # Clip a 1.0 per evitare che le zone chiare del template sbianchino i bordi
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
        st.warning(f"⚠️ Cartella '{base_path}' non trovata!")
        return lib
    
    for f_name in os.listdir(base_path):
        if f_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            cat = get_manual_cat(f_name)
            if cat in lib:
                try:
                    img = Image.open(os.path.join(base_path, f_name)).convert('RGB')
                    lib[cat][f_name] = img
                except Exception as e:
                    st.error(f"Errore caricamento {f_name}: {e}")
    
    return lib

@st.cache_data
def get_template_thumbnails():
    """Crea thumbnail uniformi per le anteprime - DIMENSIONI FISSE"""
    lib = load_fixed_templates()
    thumbs = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    
    # Dimensioni fisse per i thumbnail
    thumb_width = 300
    thumb_height = 300
    
    for cat in lib:
        for fname, img in lib[cat].items():
            # Resize con dimensioni fisse - l'immagine viene centrata su sfondo grigio
            thumb = Image.new('RGB', (thumb_width, thumb_height), (240, 240, 240))
            
            # Calcolo proporzioni per fit
            img_aspect = img.width / img.height
            thumb_aspect = thumb_width / thumb_height
            
            if img_aspect > thumb_aspect:
                # Immagine più larga - fit sulla larghezza
                new_width = thumb_width
                new_height = int(thumb_width / img_aspect)
            else:
                # Immagine più alta - fit sull'altezza
                new_height = thumb_height
                new_width = int(thumb_height * img_aspect)
            
            resized = img.resize((new_width, new_height), Image.LANCZOS)
            
            # Centro l'immagine
            x = (thumb_width - new_width) // 2
            y = (thumb_height - new_height) // 2
            thumb.paste(resized, (x, y))
            
            thumbs[cat][fname] = thumb
    
    return lib, thumbs

libreria, thumbnails = get_template_thumbnails()

# --- INTERFACCIA ---
st.title("📖 PhotoBook Mockup Compositor - V3 Fixed (No White Lines)")

# Pulsante per ricaricare i template
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

st.subheader("⚡ Produzione")
col_sel, col_del = st.columns([3, 1])
with col_sel:
    scelta = st.radio("Seleziona formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
with col_del:
    if st.button("🗑️ SVUOTA DESIGN"):
        st.session_state.uploader_key += 1
        st.rerun()

disegni = st.file_uploader(f"Carica design {scelta}", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")

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
                    res = composite_v3_fixed(t_img, d_img)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95, subsampling=0)
                        zip_file.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    count += 1
                    bar.progress(count / total)
        st.success("✅ Completato!")
        st.download_button("📥 SCARICA ZIP", data=zip_buf.getvalue(), file_name=f"Mockups_{scelta}.zip")

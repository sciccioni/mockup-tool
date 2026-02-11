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
    
    # Luminanza V3 originale
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
    fx1 = region['face_x1']
    spine_w = region['spine_w']
    face_w, face_h = region['face_w'], region['face_h']
    face_val = region['face_val']

    # --- NUOVO APPROCCIO: COPERTURA COMPLETA ---
    # Invece di separare dorso e face, copriamo tutto con la cover
    # e usiamo il template per modulare l'illuminazione
    
    # Usiamo l'intera larghezza del libro
    full_book_w = bx2 - bx1 + 1
    
    # Estendo anche verticalmente di qualche pixel per evitare righe bianche
    vertical_extend = 2
    extended_by1 = max(0, by1 - vertical_extend)
    extended_by2 = min(h - 1, by2 + vertical_extend)
    extended_face_h = extended_by2 - extended_by1 + 1
    
    # Resize della cover per coprire l'intero libro (esteso)
    cover_resized = np.array(
        Image.fromarray(cover.astype(np.uint8)).resize((full_book_w, extended_face_h), Image.LANCZOS)
    ).astype(np.float64)
    
    # Estraiamo il colore del dorso dal bordo sinistro della cover
    spine_strip_w = max(1, full_book_w // 20)
    spine_color = np.median(cover_resized[:, :spine_strip_w].reshape(-1, 3), axis=0)
    
    result = np.stack([tmpl_gray, tmpl_gray, tmpl_gray], axis=2)
    
    # Applichiamo la cover su tutto il libro usando il template come maschera di luce
    book_tmpl = tmpl_gray[extended_by1:extended_by2+1, bx1:bx2+1]
    book_ratio = np.minimum(book_tmpl / face_val, 1.05)
    
    for c in range(3):
        result[extended_by1:extended_by2+1, bx1:bx2+1, c] = cover_resized[:, :, c] * book_ratio
            
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- CARICAMENTO ---
@st.cache_data
def load_fixed_templates():
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    base_path = "templates"
    
    if not os.path.exists(base_path):
        st.warning(f"⚠️ Cartella '{base_path}' non trovata!")
        return lib
    
    files_found = []
    for f_name in os.listdir(base_path):
        if f_name.lower().endswith(('.jpg', '.jpeg', '.png')):
            files_found.append(f_name)
            cat = get_manual_cat(f_name)
            if cat in lib:
                try:
                    img = Image.open(os.path.join(base_path, f_name)).convert('RGB')
                    lib[cat][f_name] = img
                except Exception as e:
                    st.error(f"Errore caricamento {f_name}: {e}")
    
    # Debug info
    if files_found:
        st.info(f"📁 Template trovati: {len(files_found)} - {', '.join(files_found)}")
    else:
        st.warning("⚠️ Nessun template trovato nella cartella templates/")
    
    return lib

@st.cache_data
def get_template_thumbnails():
    """Crea thumbnail uniformi per le anteprime"""
    lib = load_fixed_templates()
    thumbs = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    
    max_height = 250
    for cat in lib:
        for fname, img in lib[cat].items():
            aspect = img.width / img.height
            if img.height > max_height:
                new_height = max_height
                new_width = int(new_height * aspect)
                thumb = img.resize((new_width, new_height), Image.LANCZOS)
            else:
                thumb = img
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

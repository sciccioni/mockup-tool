import streamlit as st
import numpy as np
from PIL import Image, ImageOps
import os
import io
import zipfile

# --- 1. CONFIGURAZIONE E MEMORIA ---
st.set_page_config(page_title="PhotoBook PRO", layout="wide")

# Inizializzazione MEMORIA PERSISTENTE
if 'libreria' not in st.session_state:
    st.session_state['libreria'] = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}

# Chiave dinamica per resettare l'upload dei design
if 'design_uploader_key' not in st.session_state:
    st.session_state['design_uploader_key'] = 0

# --- 2. LOGICA DI ELABORAZIONE CON MARGINE (AGGIORNATA) ---
def find_book_region(tmpl_gray, bg_val):
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 5)
    rows = np.any(book_mask, axis=1); cols = np.any(book_mask, axis=0)
    if not rows.any() or not cols.any(): return None
    by1, by2 = np.where(rows)[0][[0, -1]]; bx1, bx2 = np.where(cols)[0][[0, -1]]
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    face_x1 = bx1
    for x in range(bx1, bx2 - 8):
        if np.all(row[x:x+8] >= 242): 
            face_x1 = x
            break
    margin = 30
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area))
    return {'y1': by1, 'y2': by2, 'x1': bx1, 'x2': bx2, 'fx1': face_x1, 'w': int(bx2 - face_x1 + 1), 'h': int(by2 - by1 + 1), 'val': face_val}

def process_image(tmpl_pil, cover_pil):
    tmpl_orig = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w = tmpl_gray.shape
    cover_rgb = cover_pil.convert('RGB')
    bg_val = float(np.median([tmpl_gray[5,5], tmpl_gray[5,w-5], tmpl_gray[h-5,5], tmpl_gray[h-5,w-5]]))
    reg = find_book_region(tmpl_gray, bg_val)
    if not reg: return None

    # --- NUOVA LOGICA: AGGIUNTA MARGINE BIANCO ---
    # Percentuale di margine (es. 0.05 = 5% per lato)
    padding_pct = 0.05 
    full_w, full_h = reg['w'], reg['h']
    
    # Calcola dimensioni ridotte per il design
    pad_w = int(full_w * (1 - padding_pct * 2))
    pad_h = int(full_h * (1 - padding_pct * 2))
    
    # 1. Crea sfondo bianco (colore carta)
    page_bg = Image.new('RGB', (full_w, full_h), color=(245, 245, 245))
    
    # 2. Ridimensiona il design per stare nell'area ridotta (senza stretch)
    cover_resized = ImageOps.fit(cover_rgb, (pad_w, pad_h), Image.LANCZOS)
    
    # 3. Incolla il design centrato sullo sfondo bianco
    paste_x = (full_w - pad_w) // 2
    paste_y = (full_h - pad_h) // 2
    page_bg.paste(cover_resized, (paste_x, paste_y))
    
    # Converti il risultato (design + bordo bianco) in array per l'elaborazione
    cover_res = np.array(page_bg).astype(np.float64)

    # Calcola il colore dello spine prendendolo dal design ridimensionato (non dal bordo bianco)
    spine_source_strip = np.array(cover_resized)[:, :max(1, pad_w//40)].reshape(-1, 3)
    spine_color = np.median(spine_source_strip, axis=0)
    # --- FINE NUOVA LOGICA ---

    result = tmpl_orig.copy()
    face_area_tmpl = tmpl_gray[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1]
    face_ratio = np.expand_dims(np.minimum(face_area_tmpl / reg['val'], 1.05), axis=2)
    spine_area_tmpl = tmpl_gray[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1']]
    spine_ratio = np.expand_dims(spine_area_tmpl / reg['val'], axis=2)
    
    # Applica la composizione (design + bordo) sulla faccia del libro
    result[reg['y1']:reg['y2']+1, reg['fx1']:reg['x2']+1, :] = cover_res * face_ratio
    
    if reg['fx1'] > reg['x1']:
        result[reg['y1']:reg['y2']+1, reg['x1']:reg['fx1'], :] = spine_color * spine_ratio
    
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("📂 Gestione Libreria")
    target_cat = st.selectbox("Categoria di destinazione:", ["Verticali", "Orizzontali", "Quadrati"])
    uploaded_files = st.file_uploader("Trascina i template bianchi", accept_multiple_files=True)
    
    if st.button("💾 CARICA NELLA LIBRERIA"):
        if uploaded_files:
            for f in uploaded_files:
                img = Image.open(f).convert('RGB')
                st.session_state['libreria'][target_cat][f.name] = img
            st.success("Libreria aggiornata!")
        else:
            st.error("Seleziona i file!")

    st.divider()
    if st.button("🗑️ SVUOTA TUTTA LA LIBRERIA"):
        st.session_state['libreria'] = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
        st.rerun()

# --- 4. MAIN PAGE ---
st.title("📖 PhotoBook Composer PRO")

# Galleria Anteprime
st.subheader("🖼️ Template salvati in memoria")
tabs = st.tabs(["Verticali", "Orizzontali", "Quadrati"])

for i, cat_name in enumerate(["Verticali", "Orizzontali", "Quadrati"]):
    with tabs[i]:
        tmpls_dict = st.session_state['libreria'][cat_name]
        if not tmpls_dict:
            st.info(f"Nessun template {cat_name} in memoria.")
        else:
            grid = st.columns(5)
            for idx, (name, img) in enumerate(tmpls_dict.items()):
                grid[idx % 5].image(img, caption=name, use_container_width=True)

st.divider()

# --- SEZIONE PRODUZIONE ---
st.subheader("⚡ Produzione Mockup")
c1, c2 = st.columns([2, 1])

with c1:
    prod_cat = st.radio("Seleziona formato grafiche:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)

with c2:
    if st.button("🧹 CANCELLA TUTTE LE GRAFICHE"):
        st.session_state['design_uploader_key'] += 1
        st.rerun()

designs = st.file_uploader(
    f"Trascina qui le grafiche {prod_cat}", 
    accept_multiple_files=True, 
    key=f"design_upload_{st.session_state['design_uploader_key']}"
)

if designs:
    st.success(f"📦 {len(designs)} immagini caricate. Verranno applicate con un bordo bianco di sicurezza.")
    with st.expander("👁️ Clicca per vedere anteprima grafiche caricate"):
        p_cols = st.columns(5)
        for i, d in enumerate(designs[:10]):
            p_cols[i % 5].image(Image.open(d), use_container_width=True)

if st.button("🚀 AVVIA GENERAZIONE"):
    active_tmpls = st.session_state['libreria'][prod_cat]
    if not active_tmpls or not designs:
        st.error("Errore: Assicurati di avere template in libreria e grafiche caricate!")
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            progress = st.progress(0)
            status = st.empty()
            total = len(designs) * len(active_tmpls)
            count = 0
            for d_file in designs:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                for t_name, t_img in active_tmpls.items():
                    status.text(f"Elaborazione: {d_name} su {t_name}")
                    res = process_image(t_img, d_img)
                    if res:
                        img_io = io.BytesIO()
                        res.save(img_io, format='JPEG', quality=90)
                        zip_file.writestr(f"{d_name}/{t_name}.jpg", img_io.getvalue())
                    count += 1
                    progress.progress(count / total)
        
        st.success(f"✅ Creati {count} mockup con bordo!")
        st.download_button("📥 SCARICA ZIP", data=zip_buffer.getvalue(), file_name=f"Mockups_{prod_cat}.zip")

import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageOps
import os
import io
import zipfile

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup - Fixed Coords", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- COORDINATE FISSE ---
TEMPLATE_COORDS = {
    "15x22-crea la tua grafica.jpg": (1195, 729, 1537, 1232, 246.0, 12),
    # Aggiungi gli altri template qui sotto...
}

# --- SMISTAMENTO CATEGORIE ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["base_copertina_verticale", "base_verticale_temi_app", "base_bottom_app", "15x22", "20x30"]): 
        return "Verticali"
    if any(x in fn for x in ["base_copertina_orizzontale", "base_orizzontale_temi_app", "20x15", "27x20", "32x24", "40x30"]): 
        return "Orizzontali"
    if any(x in fn for x in ["base_quadrata_temi_app", "20x20", "30x30"]): 
        return "Quadrati"
    return "Altro"

# --- COMPOSIZIONE CON COORDINATE FISSE ---
def composite_fixed(tmpl_pil, cover_pil, template_name=""):
    """Composizione usando SOLO coordinate fisse"""
    
    # Trova coordinate per questo template
    coords_data = TEMPLATE_COORDS.get(template_name)
    
    if coords_data is None:
        st.error(f"❌ Coordinate mancanti per: {template_name}")
        return None
    
    bx1, by1, bx2, by2, face_val, bleed = coords_data
    
    # 1. Prepara cover con blur
    cover_pil = cover_pil.convert('RGB').filter(ImageFilter.GaussianBlur(radius=1))
    
    # 2. Converti template in array
    tmpl = np.array(tmpl_pil).astype(np.float64)
    tmpl_gray = (0.299 * tmpl[:,:,0] + 0.587 * tmpl[:,:,1] + 0.114 * tmpl[:,:,2]) if tmpl.ndim == 3 else tmpl
    
    # 3. Calcola dimensioni target
    target_w = bx2 - bx1 + 1
    target_h = by2 - by1 + 1
    
    # 4. Fit intelligente con bleed
    full_w = target_w + bleed * 2
    full_h = target_h + bleed * 2
    
    cover_fitted = ImageOps.fit(
        cover_pil, 
        (full_w, full_h), 
        method=Image.LANCZOS, 
        centering=(0.5, 0.5)
    )
    
    # 5. Ritaglia la parte centrale (rimuovi bleed)
    cover_res = np.array(cover_fitted).astype(np.float64)
    cover_final = cover_res[bleed:bleed+target_h, bleed:bleed+target_w]
    
    # 6. Crea risultato
    result = np.stack([tmpl_gray] * 3, axis=2)
    
    # 7. Applica ombreggiatura del template
    book_region = tmpl_gray[by1:by2+1, bx1:bx2+1]
    book_ratio = np.minimum(book_region / face_val, 1.0)
    
    # 8. Inserisci cover con ombreggiatura
    for c in range(3):
        result[by1:by2+1, bx1:bx2+1, c] = cover_final[:, :, c] * book_ratio
    
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

# --- CARICAMENTO ---
@st.cache_data
def load_templates():
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    if not os.path.exists("templates"): 
        return lib
    
    for f in os.listdir("templates"):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            cat = get_manual_cat(f)
            if cat in lib:
                lib[cat][f] = Image.open(os.path.join("templates", f)).convert('RGB')
    
    return lib

libreria = load_templates()

# --- INTERFACCIA ---
st.title("🎯 Mockup Engine - Fixed Coordinates")

# Info sulle coordinate caricate
if TEMPLATE_COORDS:
    st.sidebar.success(f"✅ {len(TEMPLATE_COORDS)} coordinate caricate")
    with st.sidebar.expander("📋 Template configurati"):
        for name in sorted(TEMPLATE_COORDS.keys()):
            st.write(f"• {name}")
else:
    st.sidebar.error("⚠️ Nessuna coordinata configurata!")

col1, col2 = st.columns([2, 1])
with col1:
    scelta = st.radio("Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
with col2:
    if st.button("🗑️ Reset"):
        st.session_state.uploader_key += 1
        st.rerun()

disegni = st.file_uploader(
    "Carica design copertine", 
    accept_multiple_files=True, 
    key=f"up_{st.session_state.uploader_key}",
    type=['jpg', 'jpeg', 'png']
)

if st.button("🔥 GENERA MOCKUP"):
    if not disegni:
        st.error("⚠️ Carica almeno un design!")
    elif not libreria[scelta]:
        st.error(f"⚠️ Nessun template trovato per categoria '{scelta}'")
    else:
        target_tmpls = libreria[scelta]
        
        # Verifica che tutti i template abbiano coordinate
        missing = [name for name in target_tmpls.keys() if name not in TEMPLATE_COORDS]
        if missing:
            st.error(f"❌ Coordinate mancanti per: {', '.join(missing)}")
            st.stop()
        
        # Anteprima con primo design
        first_d = Image.open(disegni[0])
        st.subheader(f"🖼️ Anteprima: {disegni[0].name}")
        
        cols = st.columns(min(4, len(target_tmpls)))
        for idx, (t_name, t_img) in enumerate(target_tmpls.items()):
            prev = composite_fixed(t_img, first_d, t_name)
            if prev:
                cols[idx % len(cols)].image(prev, caption=t_name, use_container_width=True)
            else:
                cols[idx % len(cols)].error(f"Errore: {t_name}")
        
        # Generazione ZIP
        st.divider()
        st.subheader("📦 Generazione batch in corso...")
        
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED) as zip_f:
            bar = st.progress(0, text="Inizializzazione...")
            total = len(disegni) * len(target_tmpls)
            done = 0
            
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                
                for t_name, t_img in target_tmpls.items():
                    res = composite_fixed(t_img, d_img, t_name)
                    
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zip_f.writestr(f"{d_name}/{t_name}", buf.getvalue())
                    
                    done += 1
                    bar.progress(done / total, text=f"Elaborazione: {done}/{total}")
        
        st.success(f"✅ Generati {done} mockup!")
        st.download_button(
            "📥 SCARICA ZIP",
            zip_buf.getvalue(),
            f"Mockups_{scelta}_{len(disegni)}designs.zip",
            "application/zip"
        )

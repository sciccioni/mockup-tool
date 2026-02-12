import streamlit as st
import numpy as np
from PIL import Image
import os
import io
import zipfile

# --- 1. COORDINATE DI PARTENZA (MEMORIA) ---
TEMPLATE_MAPS = {
    "base_verticale_temi_app": (35.1, 10.4, 29.8, 79.2),
    "base_orizzontale_temi_app": (19.4, 9.4, 61.2, 81.2),
    "base_orizzontale_temi_app3": (19.4, 9.4, 61.2, 81.2),
    "base_quadrata_temi_app": (28.2, 10.4, 43.6, 77.4),
    "base_bottom_app": (22.8, 4.4, 54.8, 89.6),
}

# --- 2. MOTORE DI COMPOSIZIONE ---
def process_mockup(tmpl_pil, cover_pil, x_pct, y_pct, w_pct, h_pct):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = np.array(tmpl_pil.convert('L')).astype(np.float64)
    h, w, _ = tmpl_rgb.shape
    
    x1, y1 = int((x_pct * w) / 100), int((y_pct * h) / 100)
    tw, th = int((w_pct * w) / 100), int((h_pct * h) / 100)
    
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # Shadow Map (Multiply) per il realismo della carta e delle pieghe
    book_shadows = tmpl_gray[y1:y1+th, x1:x1+tw]
    shadow_map = np.clip(book_shadows / 255.0, 0, 1.0)
    
    result = tmpl_rgb.copy()
    for c in range(3):
        result[y1:y1+th, x1:x1+tw, c] = cover_res[:, :, c] * shadow_map
        
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["verticale", "bottom", "15x22", "20x30"]): return "Verticali"
    if any(x in fn for x in ["orizzontale", "20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["quadrata", "20x20", "30x30"]): return "Quadrati"
    return "Altro"

# --- 3. INTERFACCIA STREAMLIT ---
st.set_page_config(page_title="Mockup Precision Input", layout="wide")
st.title("📖 PhotoBook Mockup - Inserimento Manuale")

@st.cache_data
def load_lib():
    path = "templates"
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}}
    if os.path.exists(path):
        for f in os.listdir(path):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                cat = get_manual_cat(f)
                if cat in lib: lib[cat][f] = Image.open(os.path.join(path, f))
    return lib

libreria = load_lib()

# Tab dei template
tabs = st.tabs(["📂 Verticali", "📂 Orizzontali", "📂 Quadrati"])
for i, (tab, name) in enumerate(zip(tabs, ["Verticali", "Orizzontali", "Quadrati"])):
    with tab:
        cols = st.columns(5)
        for idx, f_name in enumerate(libreria[name].keys()):
            cols[idx % 5].image(libreria[name][f_name], caption=f_name, use_column_width=True)

st.divider()

# --- SEZIONE CALIBRAZIONE MANUALE ---
st.subheader("🚀 Configurazione e Produzione")

col_settings, col_upload = st.columns([2, 2])

with col_settings:
    st.markdown("### 1. Inserimento Coordinate (Pixel %)")
    categoria = st.selectbox("Seleziona Formato:", ["Verticali", "Orizzontali", "Quadrati"])
    
    if libreria[categoria]:
        t_nome = st.selectbox("Scegli Template:", list(libreria[categoria].keys()))
        
        # Recupero i valori di default
        app_key = next((k for k in TEMPLATE_MAPS.keys() if k in t_nome.lower()), None)
        defaults = TEMPLATE_MAPS.get(app_key, (0.0, 0.0, 100.0, 100.0))
        
        # --- INPUT MANUALI ---
        c1, c2 = st.columns(2)
        with c1:
            val_x = st.number_input("X (Inizio Orizzontale %)", value=float(defaults[0]), step=0.1, format="%.1f")
            val_w = st.number_input("Larghezza (%)", value=float(defaults[2]), step=0.1, format="%.1f")
        with c2:
            val_y = st.number_input("Y (Inizio Verticale %)", value=float(defaults[1]), step=0.1, format="%.1f")
            val_h = st.number_input("Altezza (%)", value=float(defaults[3]), step=0.1, format="%.1f")
            
        st.info("💡 Copia questa riga nel dizionario TEMPLATE_MAPS per salvare:")
        st.code(f"'{t_nome}': ({val_x}, {val_y}, {val_w}, {val_h}),", language='python')
    else:
        st.warning("Nessun template trovato.")

with col_upload:
    st.markdown("### 2. Carica Design")
    disegni = st.file_uploader("Trascina qui le grafiche:", accept_multiple_files=True)
    
    if disegni and libreria[categoria]:
        if st.button("🚀 GENERA E SCARICA ZIP"):
            zip_io = io.BytesIO()
            with zipfile.ZipFile(zip_io, "a") as zf:
                for f in disegni:
                    res = process_mockup(libreria[categoria][t_nome], Image.open(f), val_x, val_y, val_w, val_h)
                    buf = io.BytesIO()
                    res.save(buf, format='JPEG', quality=95)
                    zf.writestr(f"Mockup_{f.name}", buf.getvalue())
            
            st.download_button("📥 SCARICA ZIP", zip_io.getvalue(), f"Mockups_{t_nome}.zip")

# --- ANTEPRIMA ---
if disegni and libreria[categoria]:
    st.divider()
    st.subheader("👁️ Anteprima Risultato")
    preview = process_mockup(libreria[categoria][t_nome], Image.open(disegni[-1]), val_x, val_y, val_w, val_h)
    st.image(preview, use_column_width=True)

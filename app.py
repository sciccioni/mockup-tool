import streamlit as st
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import os
import io
import zipfile

# --- 1. MAPPA COORDINATE (CALIBRATE PER STARE DENTRO I BORDI) ---
TEMPLATE_MAPS = {
    "base_verticale_temi_app.jpg": (34.6, 9.2, 30.2, 80.3),
    "base_bottom_app.jpg": (21.9, 4.9, 56.5, 91.3),
    "base_orizzontale_temi_app.jpg": (18.9, 9.4, 61.8, 83.0),
    "base_orizzontale_temi_app3.jpg": (18.7, 9.4, 62.2, 82.6),
    "base_quadrata_temi_app.jpg": (27.8, 10.8, 44.5, 79.0),
    
    # Formati Standard: NON più 0,0,100,100 (che usciva dai bordi)
    # Ma calibrate per stare "dentro" la cornice del foglio
    "base_copertina_verticale.jpg": (2.0, 2.0, 96.0, 96.0),
    "base_copertina_orizzontale.jpg": (2.0, 2.0, 96.0, 96.0),
    "15x22-crea la tua grafica.jpg": (3.0, 3.0, 94.0, 94.0),
    "20x30-crea la tua grafica.jpg": (3.0, 3.0, 94.0, 94.0),
    "30x30-crea la tua grafica.jpg": (15.0, 15.0, 70.0, 70.0),
}

# --- 2. LOGICA DI SMISTAMENTO ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["verticale", "bottom", "15x22", "20x30"]):
        return "Verticali"
    if any(x in fn for x in ["orizzontale", "20x15", "27x20", "32x24", "40x30"]):
        return "Orizzontali"
    if any(x in fn for x in ["quadrata", "20x20", "30x30", "quadrato"]):
        return "Quadrati"
    return "Altro"

# --- 3. MOTORE DI RENDERING (MULTIPLY ATTIVO PER TUTTI) ---
def apply_mockup(tmpl_pil, cover_pil, coords, blur_rad=5.0):
    x_pct, y_pct, w_pct, h_pct = coords
    tmpl_img = tmpl_pil.convert('RGB')
    w_f, h_f = tmpl_img.size

    x1, y1 = int((x_pct * w_f) / 100), int((y_pct * h_f) / 100)
    tw, th = int((w_pct * w_f) / 100), int((h_pct * h_f) / 100)
    tw, th = max(1, min(tw, w_f - x1)), max(1, min(th, h_f - y1))

    # Resize cover
    cover_res = np.array(cover_pil.convert('RGB').resize((tw, th), Image.LANCZOS)).astype(np.float64)
    
    # Shadow Map (MULTIPLY) - Fa vedere quello che c'è sotto
    shadow_map = np.array(tmpl_pil.convert('L').crop((x1, y1, x1+tw, y1+th))).astype(np.float64) / 255.0
    shadow_map = np.expand_dims(shadow_map, axis=2)

    # Maschera sfumatura bordi
    mask = Image.new("L", (tw, th), 255)
    if blur_rad > 0:
        draw = ImageDraw.Draw(mask)
        draw.rectangle([0, 0, tw, th], outline=0, width=int(blur_rad/2)+1)
        mask = mask.filter(ImageFilter.GaussianBlur(blur_rad))
    alpha = np.expand_dims(np.array(mask).astype(np.float64) / 255.0, axis=2)

    # Blending Originale
    crop_orig = np.array(tmpl_img.crop((x1, y1, x1+tw, y1+th))).astype(np.float64)
    cover_final = cover_res * shadow_map # Applica l'effetto trasparenza/ombra
    blended = (cover_final * alpha) + (crop_orig * (1 - alpha))

    result = np.array(tmpl_img).copy()
    result[y1:y1+th, x1:x1+tw] = np.clip(blended, 0, 255).astype(np.uint8)
    return Image.fromarray(result)

# --- 4. INTERFACCIA STREAMLIT ---
st.set_page_config(page_title="PhotoBook Master V7.9", layout="wide")
st.title("📖 PhotoBook Master V7.9")

@st.cache_data
def load_library():
    path = "templates"
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}, "Tutti": {}}
    if os.path.exists(path):
        for f in os.listdir(path):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                img = Image.open(os.path.join(path, f))
                lib["Tutti"][f] = img
                cat = get_manual_cat(f)
                if cat in lib: lib[cat][f] = img
    return lib

libreria = load_library()

t_prod, t_sett = st.tabs(["🚀 PRODUZIONE BATCH", "⚙️ CALIBRAZIONE"])

with t_prod:
    col_l, col_r = st.columns([1, 2])
    with col_l:
        formato = st.radio("Categoria:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
        sfocatura = st.slider("Sfocatura Bordi:", 0.0, 10.0, 5.0, 0.5)
        
    with col_r:
        disegni = st.file_uploader("Carica le copertine:", accept_multiple_files=True)

    if disegni and libreria[formato]:
        if st.button("🚀 GENERA ZIP"):
            z_io = io.BytesIO()
            with zipfile.ZipFile(z_io, "a") as zf:
                for d in disegni:
                    d_img = Image.open(d)
                    for t_n, t_i in libreria[formato].items():
                        coords = TEMPLATE_MAPS.get(t_n, (0, 0, 100, 100))
                        res = apply_mockup(t_i, d_img, coords, sfocatura)
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zf.writestr(f"{os.path.splitext(d.name)[0]}/{t_n}", buf.getvalue())
            st.download_button("📥 SCARICA ZIP", z_io.getvalue(), "Mockups.zip")
        
        grid = st.columns(2)
        for i, (name, img) in enumerate(libreria[formato].items()):
            with grid[i % 2]:
                coords = TEMPLATE_MAPS.get(name, (0, 0, 100, 100))
                st.image(apply_mockup(img, Image.open(disegni[-1]), coords, sfocatura), caption=name)

with t_sett:
    if libreria["Tutti"]:
        t_sel = st.selectbox("Template:", list(libreria["Tutti"].keys()))
        def_coords = TEMPLATE_MAPS.get(t_sel, (0.0, 0.0, 100.0, 100.0))
        c_ctrl, c_view = st.columns([1, 2])
        with c_ctrl:
            x = st.number_input("X %", value=float(def_coords[0]), step=0.1)
            y = st.number_input("Y %", value=float(def_coords[1]), step=0.1)
            w = st.number_input("W %", value=float(def_coords[2]), step=0.1)
            h = st.number_input("H %", value=float(def_coords[3]), step=0.1)
            t_test = st.file_uploader("Test:", type=['jpg', 'png'])
            st.code(f"'{t_sel}': ({x}, {y}, {w}, {h}),")
        with c_view:
            if t_test:
                st.image(apply_mockup(libreria["Tutti"][t_sel], Image.open(t_test), (x,y,w,h)))

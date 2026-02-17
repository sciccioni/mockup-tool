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

# --- FIX CACHE: Rileva se i file nella cartella cambiano ---
def get_folder_hash(folder_path):
    if not os.path.exists(folder_path):
        return 0
    return sum(os.path.getmtime(os.path.join(folder_path, f)) for f in os.listdir(folder_path))

# --- MAPPING COORDINATE ---
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

def save_template_maps(maps):
    with open(TEMPLATE_MAPS_FILE, 'w') as f:
        json.dump(maps, f, indent=2)

TEMPLATE_MAPS = load_template_maps()

# --- SMISTAMENTO CATEGORIE (FIXED) ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["vertical", "15x22", "20x30", "bottom"]): return "Verticali"
    if any(x in fn for x in ["orizzontal", "20x15", "27x20", "32x24", "40x30"]): return "Orizzontali"
    if any(x in fn for x in ["quadrat", "20x20", "30x30"]): return "Quadrati"
    return "Altro"

# --- LOGICA CORE ---
def composite_v3_fixed(tmpl_pil, cover_pil, template_name="", border_offset=None):
    tmpl_rgb = np.array(tmpl_pil.convert('RGB')).astype(np.float64)
    tmpl_gray = (0.299 * tmpl_rgb[:,:,0] + 0.587 * tmpl_rgb[:,:,1] + 0.114 * tmpl_rgb[:,:,2])
    h, w = tmpl_gray.shape
    if template_name in TEMPLATE_MAPS:
        d = TEMPLATE_MAPS[template_name]
        px, py, pw, ph = d["coords"]
        bo = border_offset if border_offset is not None else d.get("offset", 1)
        x1, y1 = int((px * w) / 100) + bo, int((py * h) / 100) + bo
        tw, th = int((pw * w) / 100) - (bo * 2), int((ph * h) / 100) - (bo * 2)
        # Smart Crop
        t_asp, i_w, i_h = tw/th, cover_pil.size[0], cover_pil.size[1]
        if i_w/i_h > t_asp:
            nw = int(i_h * t_asp)
            crop = ((i_w - nw)//2, 0, (i_w - nw)//2 + nw, i_h)
        else:
            nh = int(i_w / t_asp)
            crop = (0, (i_h - nh)//2, i_w, (i_h - nh)//2 + nh)
        c_res = np.array(cover_pil.crop(crop).resize((tw, th), Image.LANCZOS)).astype(np.float64)
        shadows = np.clip(np.array(tmpl_pil.convert('L'))[y1:y1+th, x1:x1+tw] / 255.0, 0, 1.0)
        res = tmpl_rgb.copy()
        for c in range(3): res[y1:y1+th, x1:x1+tw, c] = c_res[:,:,c] * shadows
        return Image.fromarray(np.clip(res, 0, 255).astype(np.uint8))
    return None

def draw_rectangle_on_template(template_img, px, py, pw, ph):
    img = template_img.copy()
    draw = ImageDraw.Draw(img)
    w, h = img.size
    x1, y1 = int((px * w) / 100), int((py * h) / 100)
    x2, y2 = x1 + int((pw * w) / 100), y1 + int((ph * h) / 100)
    draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=3)
    return img

# --- CARICAMENTO LIBRERIA ---
@st.cache_data
def get_library(folder_hash):
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}, "Altro": {}}
    if not os.path.exists("templates"): return lib
    for f in os.listdir("templates"):
        if f.lower().endswith(('.jpg', '.png', '.jpeg')):
            cat = get_manual_cat(f)
            lib[cat][f] = Image.open(os.path.join("templates", f)).convert('RGB')
    return lib

libreria = get_library(get_folder_hash("templates"))

# --- INTERFACCIA ---
st.title("📖 PhotoBook Mockup Compositor - V3 Fixed")

# --- MENU LATERALE RIPRISTINATO ---
menu = st.sidebar.radio("Menu", ["📚 Templates", "🎯 Calibrazione Coordinate", "⚡ Produzione"])

if menu == "📚 Templates":
    if st.button("🔄 RICARICA TEMPLATES"):
        st.cache_data.clear()
        st.rerun()
    tabs = st.tabs(list(libreria.keys()))
    for i, cat in enumerate(libreria.keys()):
        with tabs[i]:
            if not libreria[cat]: st.info("Vuoto")
            else:
                cols = st.columns(4)
                for idx, (fn, img) in enumerate(libreria[cat].items()):
                    cols[idx % 4].image(img, caption=fn, use_column_width=True)

elif menu == "🎯 Calibrazione Coordinate":
    st.header("🎯 Calibrazione Coordinate")
    cat_choice = st.selectbox("Categoria:", list(libreria.keys()))
    selected_t = st.selectbox("Template:", list(libreria[cat_choice].keys()))
    
    if selected_t:
        t_img = libreria[cat_choice][selected_t]
        d = TEMPLATE_MAPS.get(selected_t, {"coords": (20.0, 10.0, 60.0, 80.0), "offset": 1})
        
        # State management per slider
        if 'cal_px' not in st.session_state or st.session_state.get('last_t') != selected_t:
            st.session_state.cal_px, st.session_state.cal_py = d["coords"][0], d["coords"][1]
            st.session_state.cal_pw, st.session_state.cal_ph = d["coords"][2], d["coords"][3]
            st.session_state.cal_off = d["offset"]
            st.session_state.last_t = selected_t

        c1, c2 = st.columns(2)
        st.session_state.cal_px = c1.number_input("X %", 0.0, 100.0, st.session_state.cal_px, 0.1)
        st.session_state.cal_pw = c1.number_input("Width %", 0.1, 100.0, st.session_state.cal_pw, 0.1)
        st.session_state.cal_py = c2.number_input("Y %", 0.0, 100.0, st.session_state.cal_py, 0.1)
        st.session_state.cal_ph = c2.number_input("Height %", 0.1, 100.0, st.session_state.cal_ph, 0.1)
        st.session_state.cal_off = st.slider("Border Offset", 0, 20, st.session_state.cal_off)

        t1, t2 = st.tabs(["📏 Rettangolo", "💾 Salva"])
        with t1:
            st.image(draw_rectangle_on_template(t_img, st.session_state.cal_px, st.session_state.cal_py, st.session_state.cal_pw, st.session_state.cal_ph), use_column_width=True)
        with t2:
            if st.button("💾 SALVA COORDINATE"):
                TEMPLATE_MAPS[selected_t] = {"coords": (st.session_state.cal_px, st.session_state.cal_py, st.session_state.cal_pw, st.session_state.cal_ph), "offset": st.session_state.cal_off}
                save_template_maps(TEMPLATE_MAPS)
                st.success("Salvate!")

elif menu == "⚡ Produzione":
    st.subheader("⚡ Produzione")
    scelta = st.radio("Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
    
    preview_design = st.file_uploader("Carica design per anteprima", type=['jpg', 'png'], key='prev')
    if preview_design and libreria[scelta]:
        d_img = Image.open(preview_design)
        cols = st.columns(4)
        for i, (t_name, t_img) in enumerate(libreria[scelta].items()):
            res = composite_v3_fixed(t_img, d_img, t_name)
            if res: cols[i % 4].image(res, caption=t_name, use_column_width=True)

    disegni = st.file_uploader("Batch", accept_multiple_files=True, key=f"up_{st.session_state.uploader_key}")
    if st.button("🚀 GENERA TUTTI") and disegni and libreria[scelta]:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED) as zf:
            bar = st.progress(0)
            total = len(disegni) * len(libreria[scelta])
            count = 0
            for d_file in disegni:
                d_img = Image.open(d_file)
                d_name = os.path.splitext(d_file.name)[0]
                for t_name, t_img in libreria[scelta].items():
                    res = composite_v3_fixed(t_img, d_img, t_name)
                    if res:
                        buf = io.BytesIO()
                        res.save(buf, format='JPEG', quality=95)
                        zf.writestr(f"{d_name}/{t_name}.jpg", buf.getvalue())
                    count += 1
                    bar.progress(count / total)
        st.session_state.zip_ready = True
        st.session_state.zip_data = zip_buf.getvalue()
        st.success("Completato!")

    if st.session_state.get('zip_ready'):
        st.download_button("📥 SCARICA ZIP", st.session_state.zip_data, f"Mockups_{scelta}.zip", "application/zip")

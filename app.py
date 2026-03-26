import streamlit as st
import numpy as np
from PIL import Image, ImageDraw
import os
import io
import zipfile
import json
import requests
import base64

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="PhotoBook Mockup Compositor - V3 FIXED", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- ANTI-CACHE ---
def get_folder_hash(folder_path):
    if not os.path.exists(folder_path):
        return 0
    return sum(os.path.getmtime(os.path.join(folder_path, f)) for f in os.listdir(folder_path))

# --- COORDINATE ---
TEMPLATE_MAPS_FILE = "template_coordinates.json"
GITHUB_REPO = "sciccioni/mockup-tool"
GITHUB_PATH = "template_coordinates.json"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"

DEFAULT_MAPS = {
    "base_verticale_temi_app.jpg": {"coords": (34.4, 9.1, 30.6, 80.4), "offset": 1},
    "base_orizzontale_temi_app.jpg": {"coords": (18.9, 9.4, 61.9, 83.0), "offset": 1},
    "base_orizzontale_temi_app3.jpg": {"coords": (18.7, 9.4, 62.2, 82.9), "offset": 1},
    "base_quadrata_temi_app.jpg": {"coords": (27.7, 10.5, 44.7, 44.7), "offset": 1},
    "base_bottom_app.jpg": {"coords": (21.8, 4.7, 57.0, 91.7), "offset": 1},
    "15x22-crea la tua grafica.jpg": {"coords": (33.1, 21.4, 33.9, 57.0), "offset": 2},
    "20x30-crea la tua grafica.jpg": {"coords": (33.1, 21.4, 33.9, 57.0), "offset": 2},
    "Fotolibro-Temi-Verticali-temi-2.png": {"coords": (13.6, 4.0, 73.0, 92.0), "offset": 1},
    "Fotolibro-Temi-Verticali-temi-3.png": {"coords": (13.6, 4.0, 73.0, 92.0), "offset": 1},
    "orrizontale-preview-app.png": {"coords": (3.17, 4.51, 92.16, 90.0), "offset": 1}
}

def get_github_headers():
    token = st.secrets.get("GITHUB_TOKEN", "")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

def load_template_maps():
    try:
        resp = requests.get(GITHUB_API, headers=get_github_headers(), timeout=5)
        if resp.status_code == 200:
            content = resp.json().get("content", "")
            decoded = base64.b64decode(content).decode("utf-8")
            return json.loads(decoded)
    except Exception:
        pass
    # fallback: prova file locale
    if os.path.exists(TEMPLATE_MAPS_FILE):
        try:
            with open(TEMPLATE_MAPS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_MAPS

def save_template_maps(maps):
    content = json.dumps(maps, indent=2)
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    headers = get_github_headers()

    # recupera SHA del file attuale (necessario per aggiornare)
    sha = None
    try:
        resp = requests.get(GITHUB_API, headers=headers, timeout=5)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
    except Exception:
        pass

    payload = {
        "message": "Update template_coordinates.json",
        "content": encoded,
        "branch": "main"
    }
    if sha:
        payload["sha"] = sha

    try:
        resp = requests.put(GITHUB_API, headers=headers, json=payload, timeout=10)
        if resp.status_code in (200, 201):
            return True
    except Exception:
        pass

    # fallback: salva in locale se GitHub fallisce
    try:
        with open(TEMPLATE_MAPS_FILE, 'w') as f:
            f.write(content)
    except Exception:
        pass
    return False

TEMPLATE_MAPS = load_template_maps()

# --- CATEGORIE ---
def get_manual_cat(filename):
    fn = filename.lower()
    if any(x in fn for x in ["vertical", "15x22", "20x30", "bottom", "copertina_verticale"]):
        return "Verticali"
    if any(x in fn for x in ["orizzontal", "orrizontale", "orrizontale-preview-app", "20x15", "27x20", "32x24", "40x30"]):
        return "Orizzontali"
    if any(x in fn for x in ["quadrat", "20x20", "30x30"]):
        return "Quadrati"
    return "Altro"

# --- CORE LOGIC ---
def find_book_region(tmpl_gray, bg_val):
    h, w = tmpl_gray.shape
    book_mask = tmpl_gray > (bg_val + 3)
    rows, cols = np.any(book_mask, axis=1), np.any(book_mask, axis=0)
    if not rows.any() or not cols.any():
        return None
    by1, by2 = np.where(rows)[0][[0, -1]]
    bx1, bx2 = np.where(cols)[0][[0, -1]]
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    face_x1 = bx1
    for x in range(bx1, bx2 - 5):
        if np.all(row[x:x+5] >= 240):
            face_x1 = x
            break
    return {
        'book_x1': int(bx1), 'book_x2': int(bx2),
        'book_y1': int(by1), 'book_y2': int(by2),
        'face_x1': int(face_x1)
    }

def composite_v3_fixed(tmpl_pil, cover_pil, template_name="", border_offset=None):
    has_alpha = False
    alpha_mask = None
    if (tmpl_pil.mode in ('RGBA', 'LA') or
            (tmpl_pil.mode == 'P' and 'transparency' in tmpl_pil.info) or
            template_name.lower().endswith('.png')):
        has_alpha = True
        tmpl_pil = tmpl_pil.convert('RGBA')
        alpha_mask = tmpl_pil.split()[3]

    tmpl_rgb = tmpl_pil.convert('RGB')
    h, w = tmpl_rgb.size[1], tmpl_rgb.size[0]

    if template_name in TEMPLATE_MAPS:
        d = TEMPLATE_MAPS[template_name]
        px, py, pw, ph = d["coords"]
        bo = border_offset if border_offset is not None else d.get("offset", 1)
        x1, y1 = int((px * w) / 100) + bo, int((py * h) / 100) + bo
        tw, th = int((pw * w) / 100) - (bo * 2), int((ph * h) / 100) - (bo * 2)
        target_aspect = tw / th
        cw, ch = cover_pil.size
        if cw/ch > target_aspect:
            nw = int(ch * target_aspect)
            crop = ((cw - nw)//2, 0, (cw - nw)//2 + nw, ch)
        else:
            nh = int(cw / target_aspect)
            crop = (0, (ch - nh)//2, cw, (ch - nh)//2 + nh)
        c_res = cover_pil.crop(crop).resize((tw, th), Image.LANCZOS)
        tmpl_l = np.array(tmpl_rgb.convert('L')).astype(np.float64)
        shadows = np.clip(tmpl_l[y1:y1+th, x1:x1+tw] / 246.0, 0, 1.0)
        c_array = np.array(c_res.convert('RGB')).astype(np.float64)
        for i in range(3):
            c_array[:,:,i] *= shadows
        final_face = Image.fromarray(c_array.astype(np.uint8))
        if c_res.mode == 'RGBA':
            tmpl_rgb.paste(final_face, (x1, y1), c_res)
        else:
            tmpl_rgb.paste(final_face, (x1, y1))
        if has_alpha:
            tmpl_rgb.putalpha(alpha_mask)
        return tmpl_rgb

    tmpl_gray = np.array(tmpl_rgb.convert('L'))
    corners = [tmpl_gray[3,3], tmpl_gray[3,w-3], tmpl_gray[h-3,3], tmpl_gray[h-3,w-3]]
    bg_val = float(np.median(corners))
    region = find_book_region(tmpl_gray, bg_val)
    if region is None or (region['book_x2'] - region['book_x1'] > w * 0.95):
        margin_x, margin_y = int(w * 0.2), int(h * 0.1)
        bx1, bx2, by1, by2 = margin_x, w - margin_x, margin_y, h - margin_y
    else:
        bx1, bx2, by1, by2 = region['book_x1'], region['book_x2'], region['book_y1'], region['book_y2']

    if "base_copertina" in template_name.lower():
        bx1, bx2, by1, by2 = 0, w-1, 0, h-1
        for x in range(w):
            if np.any(tmpl_gray[:, x] < 250):
                bx1 = x
                break
        for x in range(w-1, -1, -1):
            if np.any(tmpl_gray[:, x] < 250):
                bx2 = x
                break
        for y in range(h):
            if np.any(tmpl_gray[y, :] < 250):
                by1 = y
                break
        for y in range(h-1, -1, -1):
            if np.any(tmpl_gray[y, :] < 250):
                by2 = y
                break

    bx1, bx2 = max(0, bx1 - 2), min(w - 1, bx2 + 2)
    by1, by2 = max(0, by1 - 2), min(h - 1, by2 + 2)
    tw, th = bx2 - bx1 + 1, by2 - by1 + 1
    c_res = cover_pil.resize((tw, th), Image.LANCZOS)
    c_arr = np.array(c_res.convert('RGB')).astype(np.float64)
    sh = np.clip(tmpl_gray[by1:by2+1, bx1:bx2+1] / 246.0, 0, 1.0)
    for i in range(3):
        c_arr[:,:,i] *= sh
    final_face = Image.fromarray(c_arr.astype(np.uint8))
    if c_res.mode == 'RGBA':
        tmpl_rgb.paste(final_face, (bx1, by1), c_res)
    else:
        tmpl_rgb.paste(final_face, (bx1, by1))
    if has_alpha:
        tmpl_rgb.putalpha(alpha_mask)
    return tmpl_rgb

# --- LIBRERIA ---
@st.cache_data
def get_lib(h_val):
    lib = {"Verticali": {}, "Orizzontali": {}, "Quadrati": {}, "Altro": {}}
    if not os.path.exists("templates"):
        return lib
    for f in os.listdir("templates"):
        if f.lower().endswith(('.jpg', '.png', '.jpeg')):
            lib[get_manual_cat(f)][f] = Image.open(os.path.join("templates", f))
    return lib

libreria = get_lib(get_folder_hash("templates"))

# --- INTERFACCIA ---
menu = st.sidebar.radio("Menu", ["📚 Templates", "🎯 Calibrazione", "⚡ Produzione"])

if menu == "📚 Templates":
    st.subheader("📚 Libreria Templates")

    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        if st.button("🔄 RICARICA"):
            st.cache_data.clear()
            st.rerun()

    st.divider()

    # --- UPLOAD NUOVI TEMPLATE ---
    with st.expander("➕ Aggiungi / Sostituisci Template", expanded=False):
        uploaded_templates = st.file_uploader(
            "Carica uno o più template (JPG, PNG)",
            type=['jpg', 'jpeg', 'png'],
            accept_multiple_files=True,
            key=f"tmpl_upload_{st.session_state.uploader_key}"
        )

        if uploaded_templates:
            existing = os.listdir("templates") if os.path.exists("templates") else []
            sostituzioni = [f.name for f in uploaded_templates if f.name in existing]
            nuovi = [f.name for f in uploaded_templates if f.name not in existing]

            if sostituzioni:
                st.warning(f"⚠️ Questi file verranno **sostituiti**: {', '.join(sostituzioni)}")
            if nuovi:
                st.info(f"✅ Nuovi template: {', '.join(nuovi)}")

            if st.button("💾 SALVA TEMPLATE"):
                os.makedirs("templates", exist_ok=True)
                salvati = []
                for f in uploaded_templates:
                    dest = os.path.join("templates", f.name)
                    with open(dest, "wb") as out:
                        out.write(f.getbuffer())
                    salvati.append(f.name)
                st.success(f"Salvati: {', '.join(salvati)}")
                st.session_state.uploader_key += 1
                st.cache_data.clear()
                st.rerun()

    # --- ELIMINA TEMPLATE ---
    with st.expander("🗑️ Elimina Template", expanded=False):
        all_templates = []
        if os.path.exists("templates"):
            all_templates = [f for f in os.listdir("templates") if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

        if all_templates:
            da_eliminare = st.multiselect("Seleziona template da eliminare:", all_templates)
            if da_eliminare and st.button("🗑️ ELIMINA SELEZIONATI", type="primary"):
                for fn in da_eliminare:
                    path = os.path.join("templates", fn)
                    if os.path.exists(path):
                        os.remove(path)
                st.success(f"Eliminati: {', '.join(da_eliminare)}")
                st.cache_data.clear()
                st.rerun()
        else:
            st.info("Nessun template presente.")

    st.divider()

    # --- VISUALIZZAZIONE LIBRERIA ---
    ts = st.tabs(list(libreria.keys()))
    for i, c in enumerate(libreria.keys()):
        with ts[i]:
            cols = st.columns(4)
            for idx, (fn, img) in enumerate(libreria[c].items()):
                cols[idx%4].image(img, caption=fn, use_column_width=True)

elif menu == "🎯 Calibrazione":
    cat = st.selectbox("Categoria:", list(libreria.keys()))
    sel = st.selectbox("Template:", list(libreria[cat].keys()))
    if sel:
        t_img = libreria[cat][sel]
        d = TEMPLATE_MAPS.get(sel, {"coords": (20, 10, 60, 80), "offset": 1})
        if 'cal' not in st.session_state or st.session_state.get('cur') != sel:
            st.session_state.cal = d
            st.session_state.cur = sel
        c = list(st.session_state.cal["coords"])
        st.session_state.cal["coords"] = c
        col1, col2 = st.columns(2)
        c[0] = col1.number_input("X %", 0.0, 100.0, float(c[0]))
        c[1] = col2.number_input("Y %", 0.0, 100.0, float(c[1]))
        c[2] = col1.number_input("W %", 0.0, 100.0, float(c[2]))
        c[3] = col2.number_input("H %", 0.0, 100.0, float(c[3]))
        st.session_state.cal["offset"] = st.slider("Offset", 0, 20, int(st.session_state.cal["offset"]))
        p_img = t_img.copy().convert('RGB')
        draw = ImageDraw.Draw(p_img)
        w, h = p_img.size
        draw.rectangle(
            [int(c[0]*w/100), int(c[1]*h/100), int((c[0]+c[2])*w/100), int((c[1]+c[3])*h/100)],
            outline="red", width=5
        )
        st.image(p_img, use_column_width=True)
        if st.button("💾 SALVA"):
            TEMPLATE_MAPS[sel] = st.session_state.cal
            ok = save_template_maps(TEMPLATE_MAPS)
            if ok:
                st.success("✅ Salvate su GitHub!")
            else:
                st.warning("⚠️ Salvate in locale (GitHub non raggiungibile)")

elif menu == "⚡ Produzione":
    scelta = st.radio("Formato:", ["Verticali", "Orizzontali", "Quadrati"], horizontal=True)
    up = st.file_uploader("Carica design", type=['jpg', 'png'], key='preview')
    if up and libreria[scelta]:
        d_img = Image.open(up)
        cols = st.columns(4)
        for i, (t_name, t_img) in enumerate(libreria[scelta].items()):
            with cols[i%4]:
                res = composite_v3_fixed(t_img, d_img, t_name)
                st.image(res, caption=t_name, use_column_width=True)
    st.divider()
    batch = st.file_uploader("Batch Produzione", accept_multiple_files=True)
    if st.button("🚀 GENERA TUTTI") and batch and libreria[scelta]:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED) as zf:
            progress = st.progress(0)
            total = len(batch) * len(libreria[scelta])
            count = 0
            for b_file in batch:
                b_img = Image.open(b_file)
                base_name = os.path.splitext(b_file.name)[0]
                if base_name.lower().endswith('.png'):
                    base_name = base_name[:-4]
                for t_name, t_img in libreria[scelta].items():
                    res = composite_v3_fixed(t_img, b_img, t_name)
                    is_tmpl_png = t_name.lower().endswith('.png') or res.mode == 'RGBA'
                    save_fmt = 'PNG' if is_tmpl_png else 'JPEG'
                    save_ext = '.png' if is_tmpl_png else '.jpg'
                    buf = io.BytesIO()
                    if save_fmt == 'PNG':
                        res.save(buf, format='PNG')
                    else:
                        res.save(buf, format='JPEG', quality=95)
                    t_clean = os.path.splitext(t_name)[0]
                    if t_clean.lower().endswith('.png'):
                        t_clean = t_clean[:-4]
                    formato = t_clean.split('-')[0] if '-' in t_clean else t_clean
                    nuovo_nome = f"{formato}-{base_name}{save_ext}"
                    zf.writestr(f"{base_name}/{nuovo_nome}", buf.getvalue())
                    count += 1
                    progress.progress(count/total)
        st.session_state.zip_ready = True
        st.session_state.zip_data = zip_buf.getvalue()
        st.success("Tutto pronto!")
    if st.session_state.get('zip_ready'):
        st.download_button("📥 SCARICA ZIP", st.session_state.zip_data, f"Mockups_{scelta}.zip", "application/zip")

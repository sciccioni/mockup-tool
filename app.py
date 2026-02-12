import streamlit as st
import numpy as np
from PIL import Image, ImageDraw

st.set_page_config(layout="wide", page_title="Calibratore Ottico V2")

# --- FUNZIONI DI SUPPORTO ---
def get_initial_guess(tmpl_pil, tolerance=15):
    """Fa una stima iniziale basata sul contrasto col colore di sfondo."""
    gray = tmpl_pil.convert('L')
    arr = np.array(gray)
    h, w = arr.shape
    # Colore medio degli angoli
    bg_val = np.median([arr[:5, :5], arr[:5, -5:], arr[-5:, :5], arr[-5:, -5:]])
    mask = np.abs(arr - bg_val) > tolerance
    coords = np.argwhere(mask)
    if coords.size == 0: return 10.0, 10.0, 80.0, 80.0 # Fallback
    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)
    # Conversione in percentuali con un piccolo margine interno (-1%)
    px = max(0, round((x1 / w) * 100, 1) + 0.5)
    py = max(0, round((y1 / h) * 100, 1) + 0.5)
    pw = min(100, round(((x2 - x1) / w) * 100, 1) - 1.0)
    ph = min(100, round(((y2 - y1) / h) * 100, 1) - 1.0)
    return px, py, pw, ph

def create_preview(tmpl_img, cover_img, coords):
    """Disegna il rettangolo e, se c'è, la cover."""
    preview = tmpl_img.convert('RGB').copy()
    draw = ImageDraw.Draw(preview)
    w_f, h_f = preview.size
    
    px, py, pw, ph = coords
    x1, y1 = int((px * w_f) / 100), int((py * h_f) / 100)
    tw, th = int((pw * w_f) / 100), int((ph * h_f) / 100)
    x2, y2 = x1 + tw, y1 + th

    if cover_img:
        # Se c'è una cover, la ridimensioniamo e la incolliamo dentro
        cover_resized = cover_img.convert('RGB').resize((tw, th), Image.LANCZOS)
        # Usiamo una maschera per far vedere un po' sotto (opzionale, per ora incolliamo solido)
        preview.paste(cover_resized, (x1, y1))
        # Disegniamo il bordo rosso SOPRA la cover per controllo
        draw.rectangle([x1, y1, x2, y2], outline="red", width=5)
    else:
        # Solo rettangolo rosso spesso se non c'è cover
        draw.rectangle([x1, y1, x2, y2], outline="red", width=8)
        
    return preview

# --- INTERFACCIA ---
st.title("🎯 Calibratore Ottico di Precisione")
st.write("1. Carica il template. 2. Regola i cursori finché il rettangolo rosso non è PERFETTO. 3. (Opzionale) Carica una cover per testare.")

# Session State per mantenere i valori tra i ricaricamenti
if 'manual_coords' not in st.session_state:
    st.session_state.manual_coords = [10.0, 10.0, 80.0, 80.0]
if 'last_template' not in st.session_state:
    st.session_state.last_template = None

col_controls, col_preview = st.columns([1, 2])

with col_controls:
    st.subheader("1. Upload")
    up_tmpl = st.file_uploader("Carica Template (JPG)", type=['jpg', 'jpeg', 'png'], key="tmpl_up")
    up_cover = st.file_uploader("Carica Cover di Test (Opzionale)", type=['jpg', 'png'], key="cover_up")

    st.subheader("2. Regolazione Manuale")
    # Se carica un nuovo template, resetta la stima iniziale
    if up_tmpl and up_tmpl.name != st.session_state.last_template:
        img_tmpl_pil = Image.open(up_tmpl)
        st.session_state.manual_coords = list(get_initial_guess(img_tmpl_pil))
        st.session_state.last_template = up_tmpl.name
        st.rerun()

    # SLIDER DI CONTROLLO DIRETTO
    px = st.slider("→ Sposta X (Inizio Orizzontale %)", 0.0, 100.0, st.session_state.manual_coords[0], 0.1)
    py = st.slider("↓ Sposta Y (Inizio Verticale %)", 0.0, 100.0, st.session_state.manual_coords[1], 0.1)
    pw = st.slider("↔ Larghezza Totale (%)", 0.0, 100.0, st.session_state.manual_coords[2], 0.1)
    ph = st.slider("↕ Altezza Totale (%)", 0.0, 100.0, st.session_state.manual_coords[3], 0.1)
    
    # Aggiorna lo stato con i valori degli slider
    current_coords = [px, py, pw, ph]

    st.subheader("3. Risultato Finale")
    st.write("Copia questa riga nel tuo dizionario `TEMPLATE_MAPS`:")
    if up_tmpl:
        st.code(f"'{up_tmpl.name}': {current_coords},", language="python")
    else:
        st.code("'nome_file.jpg': [X, Y, W, H],")

with col_preview:
    st.subheader("Anteprima in Tempo Reale")
    if up_tmpl:
        img_tmpl = Image.open(up_tmpl)
        img_cover = Image.open(up_cover) if up_cover else None
        
        # Genera l'anteprima visiva
        preview_img = create_preview(img_tmpl, img_cover, current_coords)
        st.image(preview_img, use_column_width=True)
    else:
        st.info("Carica un template a sinistra per iniziare.")

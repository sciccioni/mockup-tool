import streamlit as st
import numpy as np
from PIL import Image, ImageDraw
import io

# --- FUNZIONE DI ANALISI AUTOMATICA ---
def get_auto_coords_visual(tmpl_pil, tolerance=10):
    # Trasformiamo in array per l'analisi
    img_rgb = tmpl_pil.convert('RGB')
    gray = tmpl_pil.convert('L')
    arr = np.array(gray)
    h, w = arr.shape
    
    # Identifichiamo il colore dello sfondo (mediana degli angoli)
    bg_val = np.median([arr[:5, :5], arr[:5, -5:], arr[-5:, :5], arr[-5:, -5:]])
    
    # Maschera: pixel che si scostano dallo sfondo
    mask = np.abs(arr - bg_val) > tolerance
    coords = np.argwhere(mask)
    
    if coords.size == 0:
        return None, None
    
    # Bounding Box in pixel
    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)
    
    # Coordinate in percentuali (da usare nel tuo dizionario)
    px = round((x1 / w) * 100, 1)
    py = round((y1 / h) * 100, 1)
    pw = round(((x2 - x1) / w) * 100, 1)
    ph = round(((y2 - y1) / h) * 100, 1)
    
    # Disegniamo il rettangolo rosso per il controllo visivo
    draw = ImageDraw.Draw(img_rgb)
    draw.rectangle([x1, y1, x2, y2], outline="red", width=5)
    
    return img_rgb, [px, py, pw, ph]

# --- INTERFACCIA STREAMLIT ---
st.title("🔍 Scanner Visivo di Template")
st.write("Carica un template bianco per vedere dove il sistema 'vede' il libro.")

tol = st.slider("Tolleranza Colore (abbassa se non vede i bordi, alza se vede troppo)", 1, 50, 10)
up_file = st.file_uploader("Carica Template (JPG/PNG)", type=['jpg', 'png'])

if up_file:
    img_input = Image.open(up_file)
    with st.spinner("Analisi in corso..."):
        img_viz, coords = get_auto_coords_visual(img_input, tol)
    
    if coords:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.image(img_viz, caption="Rettangolo Rosso = Area Rilevata", use_column_width=True)
            
        with col2:
            st.success("✅ Area Rilevata!")
            st.metric("X Start %", coords[0])
            st.metric("Y Start %", coords[1])
            st.metric("Larghezza %", coords[2])
            st.metric("Altezza %", coords[3])
            
            st.subheader("📝 Codice da copiare:")
            st.code(f"'{up_file.name}': {coords},")
    else:
        st.error("❌ Non riesco a trovare il libro. Prova ad abbassare la tolleranza.")

st.info("💡 Se il rettangolo rosso circonda perfettamente il libro, i numeri sono corretti. Se l'immagine finale nell'altra app è troppo grande, diminuisci manualmente i valori di Larghezza (W) e Altezza (H).")

import streamlit as st
import numpy as np
from PIL import Image
import os
import json

st.set_page_config(page_title="Template Coordinate Finder", layout="wide")

st.title("🔍 Template Coordinate Finder")
st.write("Questo tool analizza tutti i template e ti dà le coordinate da usare")

def find_book_region_auto(tmpl_pil):
    """Trova automaticamente la regione del libro"""
    tmpl = np.array(tmpl_pil).astype(np.float64)
    tmpl_gray = (0.299 * tmpl[:,:,0] + 0.587 * tmpl[:,:,1] + 0.114 * tmpl[:,:,2]) if tmpl.ndim == 3 else tmpl
    h, w = tmpl_gray.shape
    
    # Calcola background
    corners = [tmpl_gray[3,3], tmpl_gray[3,w-4], tmpl_gray[h-4,3], tmpl_gray[h-4,w-4]]
    bg_val = float(np.median(corners))
    
    # Trova la maschera del libro
    threshold = max(5, bg_val * 0.05)
    book_mask = tmpl_gray > (bg_val + threshold)
    
    rows = np.any(book_mask, axis=1)
    cols = np.any(book_mask, axis=0)
    
    if not rows.any() or not cols.any():
        return None
    
    by1, by2 = np.where(rows)[0][[0, -1]]
    bx1, bx2 = np.where(cols)[0][[0, -1]]
    
    # Trova il bordo della copertina (zona bianca)
    mid_y = (by1 + by2) // 2
    row = tmpl_gray[mid_y]
    face_x1 = bx1
    
    for x in range(bx1, min(bx2 - 5, bx1 + (bx2-bx1)//2)):
        if np.all(row[x:x + 5] >= 235):
            face_x1 = x
            break
    
    # Calcola face_val
    margin = min(30, (by2-by1)//10, (bx2-face_x1)//10)
    face_area = tmpl_gray[by1+margin:by2-margin, face_x1+margin:bx2-margin]
    face_val = float(np.median(face_area)) if face_area.size > 0 else 246.0
    
    return {
        'bx1': int(face_x1),  # Usa face_x1 come inizio X
        'by1': int(by1),
        'bx2': int(bx2),
        'by2': int(by2),
        'face_val': round(face_val, 1),
        'bg_val': round(bg_val, 1),
        'width': int(bx2 - face_x1 + 1),
        'height': int(by2 - by1 + 1)
    }

def visualize_region(img_pil, coords):
    """Disegna un rettangolo sulla regione trovata"""
    from PIL import ImageDraw
    img_copy = img_pil.copy()
    draw = ImageDraw.Draw(img_copy)
    
    # Disegna rettangolo rosso
    draw.rectangle(
        [coords['bx1'], coords['by1'], coords['bx2'], coords['by2']], 
        outline='red', 
        width=3
    )
    
    return img_copy

# Carica template
if os.path.exists("templates"):
    template_files = [f for f in os.listdir("templates") if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if template_files:
        st.success(f"✅ Trovati {len(template_files)} template")
        
        all_coords = {}
        
        for tmpl_file in sorted(template_files):
            tmpl_path = os.path.join("templates", tmpl_file)
            tmpl_img = Image.open(tmpl_path).convert('RGB')
            
            st.markdown(f"---")
            st.subheader(f"📄 {tmpl_file}")
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.write(f"**Dimensioni template:** {tmpl_img.size[0]} x {tmpl_img.size[1]} px")
                
                coords = find_book_region_auto(tmpl_img)
                
                if coords:
                    st.json(coords)
                    
                    # Determina bleed
                    is_base = any(x in tmpl_file.lower() for x in ["base_copertina", "temi_app", "base_bottom"])
                    bleed = 15 if is_base else 12
                    
                    # Salva per export
                    all_coords[tmpl_file] = {
                        'coords': (coords['bx1'], coords['by1'], coords['bx2'], coords['by2']),
                        'face_val': coords['face_val'],
                        'bleed': bleed
                    }
                    
                    st.info(f"**Bleed suggerito:** {bleed}px")
                    st.code(f'"{tmpl_file}": ({coords["bx1"]}, {coords["by1"]}, {coords["bx2"]}, {coords["by2"]}, {coords["face_val"]}, {bleed}),')
                else:
                    st.error("❌ Impossibile trovare la regione del libro")
            
            with col2:
                if coords:
                    visualized = visualize_region(tmpl_img, coords)
                    st.image(visualized, caption="Regione rilevata (rettangolo rosso)", use_container_width=True)
                else:
                    st.image(tmpl_img, use_container_width=True)
        
        # Export finale
        st.markdown("---")
        st.subheader("📋 Codice da copiare nel tuo app.py")
        
        code_output = "TEMPLATE_COORDS = {\n"
        for tmpl_file, data in all_coords.items():
            bx1, by1, bx2, by2 = data['coords']
            face_val = data['face_val']
            bleed = data['bleed']
            code_output += f'    "{tmpl_file}": ({bx1}, {by1}, {bx2}, {by2}, {face_val}, {bleed}),\n'
        code_output += "}"
        
        st.code(code_output, language='python')
        
        # Download JSON
        json_output = json.dumps(all_coords, indent=2)
        st.download_button(
            "💾 Scarica coordinate in JSON",
            json_output,
            "template_coordinates.json",
            "application/json"
        )
    else:
        st.warning("⚠️ Nessun template trovato nella cartella 'templates'")
else:
    st.error("❌ Cartella 'templates' non trovata")

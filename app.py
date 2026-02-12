import streamlit as st
import numpy as np
from PIL import Image, ImageDraw
import os

st.set_page_config(page_title="Manual Coordinate Finder", layout="wide")

st.title("🎯 Manual Template Coordinate Finder")
st.write("Clicca sui 4 angoli della copertina del libro per definire le coordinate")

# Inizializza session state
if 'selected_template' not in st.session_state:
    st.session_state.selected_template = None
if 'clicks' not in st.session_state:
    st.session_state.clicks = []
if 'all_coords' not in st.session_state:
    st.session_state.all_coords = {}

# Carica template
if os.path.exists("templates"):
    template_files = sorted([f for f in os.listdir("templates") 
                            if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
    
    if template_files:
        # Selettore template
        selected = st.selectbox("Seleziona template:", template_files)
        
        if selected != st.session_state.selected_template:
            st.session_state.selected_template = selected
            st.session_state.clicks = []
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Carica immagine
            tmpl_path = os.path.join("templates", selected)
            img = Image.open(tmpl_path).convert('RGB')
            
            st.write(f"**Dimensioni:** {img.size[0]} x {img.size[1]} px")
            
            # Istruzioni
            if len(st.session_state.clicks) == 0:
                st.info("👆 STEP 1: Clicca sull'angolo TOP-LEFT della copertina")
            elif len(st.session_state.clicks) == 1:
                st.info("👆 STEP 2: Clicca sull'angolo TOP-RIGHT della copertina")
            elif len(st.session_state.clicks) == 2:
                st.info("👆 STEP 3: Clicca sull'angolo BOTTOM-LEFT della copertina")
            elif len(st.session_state.clicks) == 3:
                st.info("👆 STEP 4: Clicca sull'angolo BOTTOM-RIGHT della copertina")
            else:
                st.success("✅ Coordinate complete!")
            
            # Mostra immagine con punti
            display_img = img.copy()
            draw = ImageDraw.Draw(display_img)
            
            # Disegna i punti cliccati
            for i, (x, y) in enumerate(st.session_state.clicks):
                color = ['red', 'blue', 'green', 'yellow'][i]
                draw.ellipse([x-5, y-5, x+5, y+5], fill=color, outline='white', width=2)
                draw.text((x+10, y-10), f"P{i+1}", fill='white')
            
            # Se abbiamo 4 punti, disegna il rettangolo
            if len(st.session_state.clicks) == 4:
                x_coords = [p[0] for p in st.session_state.clicks]
                y_coords = [p[1] for p in st.session_state.clicks]
                x1, x2 = min(x_coords), max(x_coords)
                y1, y2 = min(y_coords), max(y_coords)
                draw.rectangle([x1, y1, x2, y2], outline='cyan', width=3)
            
            st.image(display_img, use_container_width=True)
            
            # Input manuale coordinate
            st.divider()
            st.subheader("✍️ Oppure inserisci manualmente")
            
            mcol1, mcol2, mcol3, mcol4 = st.columns(4)
            with mcol1:
                manual_x1 = st.number_input("X1 (left)", 0, img.size[0], value=0, key=f"mx1_{selected}")
            with mcol2:
                manual_y1 = st.number_input("Y1 (top)", 0, img.size[1], value=0, key=f"my1_{selected}")
            with mcol3:
                manual_x2 = st.number_input("X2 (right)", 0, img.size[0], value=img.size[0], key=f"mx2_{selected}")
            with mcol4:
                manual_y2 = st.number_input("Y2 (bottom)", 0, img.size[1], value=img.size[1], key=f"my2_{selected}")
            
            if st.button("📍 Usa coordinate manuali"):
                st.session_state.clicks = [
                    (manual_x1, manual_y1),
                    (manual_x2, manual_y1),
                    (manual_x1, manual_y2),
                    (manual_x2, manual_y2)
                ]
                st.rerun()
        
        with col2:
            st.subheader("⚙️ Controlli")
            
            # Click simulator (per Streamlit Cloud dove click non funziona)
            st.write("**Aggiungi punto manualmente:**")
            click_x = st.number_input("X coordinate", 0, img.size[0], key=f"cx_{selected}")
            click_y = st.number_input("Y coordinate", 0, img.size[1], key=f"cy_{selected}")
            
            if st.button("➕ Aggiungi punto") and len(st.session_state.clicks) < 4:
                st.session_state.clicks.append((click_x, click_y))
                st.rerun()
            
            if st.button("↩️ Annulla ultimo punto") and st.session_state.clicks:
                st.session_state.clicks.pop()
                st.rerun()
            
            if st.button("🗑️ Reset punti"):
                st.session_state.clicks = []
                st.rerun()
            
            st.divider()
            
            # Se abbiamo 4 punti, calcola coordinate
            if len(st.session_state.clicks) == 4:
                x_coords = [p[0] for p in st.session_state.clicks]
                y_coords = [p[1] for p in st.session_state.clicks]
                
                bx1 = min(x_coords)
                bx2 = max(x_coords)
                by1 = min(y_coords)
                by2 = max(y_coords)
                
                st.success("✅ Coordinate calcolate!")
                
                # Calcola face_val dalla regione
                tmpl = np.array(img).astype(np.float64)
                tmpl_gray = (0.299 * tmpl[:,:,0] + 0.587 * tmpl[:,:,1] + 0.114 * tmpl[:,:,2])
                
                margin = 30
                face_area = tmpl_gray[by1+margin:by2-margin, bx1+margin:bx2-margin]
                face_val = round(float(np.median(face_area)), 1) if face_area.size > 0 else 246.0
                
                # Determina bleed
                is_base = any(x in selected.lower() for x in ["base_copertina", "temi_app", "base_bottom"])
                bleed = 15 if is_base else 12
                
                st.write("**Coordinate:**")
                st.json({
                    'x1': bx1,
                    'y1': by1,
                    'x2': bx2,
                    'y2': by2,
                    'width': bx2 - bx1 + 1,
                    'height': by2 - by1 + 1,
                    'face_val': face_val,
                    'bleed': bleed
                })
                
                # Codice da copiare
                code_line = f'"{selected}": ({bx1}, {by1}, {bx2}, {by2}, {face_val}, {bleed}),'
                st.code(code_line, language='python')
                
                # Salva nelle coordinate totali
                if st.button("💾 Salva coordinate"):
                    st.session_state.all_coords[selected] = {
                        'coords': (bx1, by1, bx2, by2),
                        'face_val': face_val,
                        'bleed': bleed
                    }
                    st.success(f"✅ Salvate per {selected}")
                    st.balloons()
        
        # Mostra tutte le coordinate salvate
        if st.session_state.all_coords:
            st.divider()
            st.subheader(f"📋 Coordinate salvate ({len(st.session_state.all_coords)} template)")
            
            # Genera codice completo
            code_output = "TEMPLATE_COORDS = {\n"
            for tmpl_name, data in sorted(st.session_state.all_coords.items()):
                bx1, by1, bx2, by2 = data['coords']
                face_val = data['face_val']
                bleed = data['bleed']
                code_output += f'    "{tmpl_name}": ({bx1}, {by1}, {bx2}, {by2}, {face_val}, {bleed}),\n'
            code_output += "}"
            
            st.code(code_output, language='python')
            
            st.download_button(
                "📥 Scarica codice Python",
                code_output,
                "template_coords.py",
                "text/plain"
            )
            
            # Lista template configurati vs mancanti
            col_ok, col_missing = st.columns(2)
            with col_ok:
                st.success(f"✅ Configurati: {len(st.session_state.all_coords)}")
                for name in sorted(st.session_state.all_coords.keys()):
                    st.write(f"  • {name}")
            
            with col_missing:
                missing = [t for t in template_files if t not in st.session_state.all_coords]
                if missing:
                    st.warning(f"⚠️ Mancanti: {len(missing)}")
                    for name in missing:
                        st.write(f"  • {name}")
                else:
                    st.success("✅ Tutti i template configurati!")
    
    else:
        st.error("❌ Nessun template trovato nella cartella 'templates'")
else:
    st.error("❌ Cartella 'templates' non trovata")

import os
import numpy as np
from PIL import Image, ImageDraw

def analyze_and_visualize(filename):
    # 1. Caricamento e analisi
    img = Image.open(filename).convert('RGB')
    gray = img.convert('L')
    arr = np.array(gray)
    h, w = arr.shape
    
    # 2. Rilevamento Bordi (Auto-threshold)
    # Prendiamo gli angoli per capire il colore dello sfondo
    bg_color = np.median([arr[:5, :5], arr[:5, -5:], arr[-5:, :5], arr[-5:, -5:]])
    
    # Creiamo una maschera di ciò che NON è lo sfondo (tolleranza 10)
    mask = np.abs(arr - bg_color) > 10
    coords = np.argwhere(mask)
    
    if coords.size == 0:
        print(f"❌ Impossibile trovare il libro in: {filename}")
        return None

    # 3. Calcolo Bounding Box (in pixel)
    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)
    
    # 4. Conversione in Percentuali (quelle che servono a te)
    px = round((x1 / w) * 100, 1)
    py = round((y1 / h) * 100, 1)
    pw = round(((x2 - x1) / w) * 100, 1)
    ph = round(((y2 - y1) / h) * 100, 1)

    # 5. DISEGNO ANTEPRIMA (Rettangolo Rosso)
    draw = ImageDraw.Draw(img)
    # Disegniamo un rettangolo rosso spesso 5px per farti vedere bene
    draw.rectangle([x1, y1, x2, y2], outline="red", width=5)
    
    # Salva il controllo visivo
    if not os.path.exists("controlli_visuali"):
        os.makedirs("controlli_visuali")
    img.save(f"controlli_visuali/CHECK_{filename}")
    
    return [px, py, pw, ph]

# --- ESECUZIONE SU TUTTI I TUOI FILE ---
files = [
    "30x30-crea la tua grafica.jpg", "15x22-crea la tua grafica.jpg",
    "20x30-crea la tua grafica.jpg", "40x30-crea la tua grafica.jpg",
    "20x15-crea la tua graficac.jpg", "32x24-crea la tua grafica.jpg",
    "27x20-crea la tua grafica.jpg", "20x20-crea la tua grafica.jpg",
    "base_verticale_temi_app.jpg", "base_bottom_app.jpg",
    "base_orizzontale_temi_app.jpg", "base_orizzontale_temi_app3.jpg",
    "base_quadrata_temi_app.jpg"
]

print("🔍 ANALISI IN CORSO...")
print("-" * 50)

final_dict = {}
for f in files:
    if os.path.exists(f):
        res = analyze_and_visualize(f)
        if res:
            final_dict[f] = res
            print(f"✅ {f} -> Coordinate: {res}")
    else:
        print(f"⚠️ File saltato (non trovato): {f}")

print("-" * 50)
print("\n🚀 COPIA E INCOLLA QUESTO NEL TUO CODICE PRINCIPALE:\n")
print("st.session_state.coords = {")
for k, v in final_dict.items():
    print(f"    '{k}': {v},")
print("}")
print("\n📂 Controlla la cartella 'controlli_visuali' per vedere i rettangoli rossi!")

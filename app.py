import os
import numpy as np
from PIL import Image

def scan_template(image_path):
    # Carichiamo in scala di grigi per analizzare i contrasti
    img = Image.open(image_path).convert('L')
    arr = np.array(img)
    h, w = arr.shape
    
    # Prendiamo il colore degli angoli come riferimento per lo sfondo
    corners = [arr[5,5], arr[5,w-5], arr[h-5,5], arr[h-5,w-5]]
    bg_val = np.median(corners)
    
    # Creiamo una maschera: cerchiamo i pixel che NON sono sfondo
    # Usiamo una tolleranza (es. 8) per ignorare il rumore del JPG
    mask = np.abs(arr - bg_val) > 8
    
    coords = np.argwhere(mask)
    if coords.size == 0:
        return [0.0, 0.0, 100.0, 100.0]
    
    # Troviamo i confini (Bounding Box)
    y1, x1 = coords.min(axis=0)
    y2, x2 = coords.max(axis=0)
    
    # Calcoliamo le percentuali rispetto al totale del file
    px = round((x1 / w) * 100, 1)
    py = round((y1 / h) * 100, 1)
    pw = round(((x2 - x1) / w) * 100, 1)
    ph = round(((y2 - y1) / h) * 100, 1)
    
    return [px, py, pw, ph]

# --- ESECUZIONE ---
templates_da_analizzare = [
    "15x22-crea la tua grafica.jpg",
    "20x30-crea la tua grafica.jpg",
    "40x30-crea la tua grafica.jpg",
    "20x15-crea la tua graficac.jpg",
    "32x24-crea la tua grafica.jpg",
    "27x20-crea la tua grafica.jpg",
    "30x30-crea la tua grafica.jpg",
    "20x20-crea la tua grafica.jpg"
]

print("--- COPIA QUESTO NEL TUO DIZIONARIO 'coords' ---")
for filename in templates_da_analizzare:
    if os.path.exists(filename):
        coords = scan_template(filename)
        print(f'"{filename}": {coords},')
    else:
        print(f'# File non trovato: {filename}')

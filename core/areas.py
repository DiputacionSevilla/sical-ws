import os
import glob
import csv
from functools import lru_cache

@lru_cache(maxsize=1)
def cargar_diccionario_areas(csv_path: str):
    """
    CSV formato: area;nombre_area  → dict de claves '01','02',...
    """
    d = {}
    if not csv_path or not os.path.exists(csv_path):
        return d
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=';')
        for row in reader:
            if not row or len(row) < 2:
                continue
            area_raw = str(row[0]).strip()
            nombre = str(row[1]).strip()
            if area_raw:
                key = area_raw.zfill(2)
                d[key] = nombre
    return d

def normalizar_area(area_val):
    if area_val is None:
        return ""
    s = str(area_val).strip()
    try:
        n = int(s)
        return f"{n:02d}"
    except Exception:
        return s.zfill(2) if s.isdigit() else s

def buscar_logo_por_area(area_code: str):
    """
    Busca archivos tipo: logo_01.png / logo_01.jpg / ...
    """
    if not area_code:
        return None
    base = f"logo_{area_code}"
    candidatos = []
    candidatos += [f"{base}{ext}" for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp")]
    candidatos += [f"logo-{area_code}{ext}" for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp")]
    candidatos += glob.glob(f"{base}.*")
    for path in candidatos:
        if os.path.exists(path) and os.path.isfile(path):
            return path
    return None

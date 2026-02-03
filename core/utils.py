import re
from datetime import datetime
from core.constants import MAX_FACTURA_LENGTH, MAX_FILENAME_LENGTH, ALLOWED_CHARS_PATTERN

_ALLOWED_RE = re.compile(ALLOWED_CHARS_PATTERN)

def sanitize_text(value: str, max_length: int = MAX_FACTURA_LENGTH) -> str:
    """
    Recorta y valida texto seguro con longitud configurable y charset limitado.
    
    Args:
        value: Texto a sanitizar
        max_length: Longitud máxima permitida (por defecto MAX_FACTURA_LENGTH)
    
    Returns:
        Texto sanitizado
        
    Raises:
        ValueError: Si el texto no cumple con los requisitos
    """
    v = (value or "").strip()
    if not v:
        raise ValueError("El valor no puede estar vacío.")
    if len(v) > max_length:
        raise ValueError(f"El valor excede la longitud máxima de {max_length} caracteres.")
    if not _ALLOWED_RE.match(v):
        raise ValueError(
            f"Valor inválido. Usa letras, números, guiones, guiones bajos, barras o puntos (1–{max_length})."
        )
    return v

def format_datetime_es(dt: datetime) -> str:
    """Formatea datetime en formato español DD/MM/YYYY HH:MM"""
    return dt.strftime("%d/%m/%Y %H:%M")

def make_safe_filename(base: str, max_length: int = MAX_FILENAME_LENGTH) -> str:
    """
    Convierte un string en un nombre de archivo seguro.
    
    Args:
        base: Nombre base del archivo
        max_length: Longitud máxima del nombre (por defecto MAX_FILENAME_LENGTH)
    
    Returns:
        Nombre de archivo seguro
    """
    base = re.sub(r"[^\w\.-]+", "_", base.strip())
    return base[:max_length] if len(base) > max_length else base

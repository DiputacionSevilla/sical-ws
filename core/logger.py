# core/logger.py
"""
Módulo de logging centralizado para la aplicación de Actas de Conformidad.
Proporciona configuración consistente de logging en todos los módulos.
"""
import logging
import sys
from typing import Optional


def setup_logger(
    name: str,
    level: int = logging.INFO,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Configura y retorna un logger con formato consistente.
    
    Args:
        name: Nombre del logger (típicamente __name__ del módulo)
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Formato personalizado (opcional)
    
    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)
    
    # Evitar duplicar handlers si ya está configurado
    if logger.handlers:
        return logger
    
    # Crear handler para stdout
    handler = logging.StreamHandler(sys.stdout)
    
    # Formato por defecto
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    formatter = logging.Formatter(format_string)
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    logger.setLevel(level)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger ya configurado o crea uno nuevo con configuración por defecto.
    
    Args:
        name: Nombre del logger
    
    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger

# core/constants.py
"""
Constantes de configuración para la aplicación de Actas de Conformidad.
Centraliza valores hardcodeados para facilitar mantenimiento y configuración.
"""

# ===========================
# PDF - Tipografías y Estilos
# ===========================
FONT_SIZE_BASE = 9
LEADING_BASE = 12
TITLE_SIZE = 11

# Espaciados verticales (pt)
SP_AFTER_TITLE = 14
SP_AFTER_ARTICLE = 12
SP_BETWEEN_BLOCKS = 12
SP_BETWEEN_ARTICLES = 10
SP_AFTER_LAST_ARTICLE = 18

# ===========================
# Archivos y Límites
# ===========================
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# ===========================
# Validación de Entrada
# ===========================
MAX_FACTURA_LENGTH = 50
MAX_FILENAME_LENGTH = 128

# Patrón para caracteres permitidos en textos sanitizados
ALLOWED_CHARS_PATTERN = r"^[\w/\-\.]{1,50}$"

# ===========================
# Rutas por Defecto
# ===========================
DEFAULT_ORACLE_CLIENT_DIR = r"C:\oracle\instantclient_19_23"
DEFAULT_LOGO_DIR = "images"
DEFAULT_LOGO_HACIENDA = "logo-hacienda.png"

# ===========================
# Zona Horaria
# ===========================
DEFAULT_TIMEZONE = "Europe/Madrid"

# ===========================
# Base de Datos
# ===========================
DEFAULT_ORACLE_PORT = 1521
DEFAULT_ORACLE_HOST = "localhost"

# Tabla y columnas para validación de usuario (pueden sobrescribirse con .env)
DEFAULT_USER_TABLE = "USUARIO"
DEFAULT_USER_COLUMN = "USUARIO"
DEFAULT_PASS_COLUMN = "PASSWORD"

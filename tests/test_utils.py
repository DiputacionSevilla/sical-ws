# tests/test_utils.py
"""
Tests unitarios para el módulo core.utils
"""
import pytest
from datetime import datetime
from core.utils import sanitize_text, format_datetime_es, make_safe_filename


class TestSanitizeText:
    """Tests para la función sanitize_text"""
    
    def test_sanitize_text_valid(self):
        """Debe aceptar texto válido"""
        assert sanitize_text("ABC123") == "ABC123"
        assert sanitize_text("test-file.pdf") == "test-file.pdf"
        assert sanitize_text("2025/000123") == "2025/000123"
    
    def test_sanitize_text_strips_whitespace(self):
        """Debe eliminar espacios al inicio y final"""
        assert sanitize_text("  ABC123  ") == "ABC123"
    
    def test_sanitize_text_empty_raises_error(self):
        """Debe lanzar error si el texto está vacío"""
        with pytest.raises(ValueError, match="no puede estar vacío"):
            sanitize_text("")
        with pytest.raises(ValueError, match="no puede estar vacío"):
            sanitize_text("   ")
    
    def test_sanitize_text_too_long_raises_error(self):
        """Debe lanzar error si excede longitud máxima"""
        with pytest.raises(ValueError, match="excede la longitud máxima"):
            sanitize_text("A" * 100)
    
    def test_sanitize_text_custom_max_length(self):
        """Debe respetar longitud máxima personalizada"""
        assert sanitize_text("ABC", max_length=10) == "ABC"
        with pytest.raises(ValueError):
            sanitize_text("ABCDEFGHIJK", max_length=10)
    
    def test_sanitize_text_invalid_chars_raises_error(self):
        """Debe rechazar caracteres no permitidos"""
        with pytest.raises(ValueError, match="Valor inválido"):
            sanitize_text("test@file")
        with pytest.raises(ValueError, match="Valor inválido"):
            sanitize_text("test file")  # espacios no permitidos


class TestFormatDatetimeEs:
    """Tests para la función format_datetime_es"""
    
    def test_format_datetime_es(self):
        """Debe formatear datetime en formato español"""
        dt = datetime(2025, 11, 26, 9, 30)
        assert format_datetime_es(dt) == "26/11/2025 09:30"
    
    def test_format_datetime_es_with_seconds(self):
        """Debe ignorar segundos en el formato"""
        dt = datetime(2025, 11, 26, 9, 30, 45)
        assert format_datetime_es(dt) == "26/11/2025 09:30"


class TestMakeSafeFilename:
    """Tests para la función make_safe_filename"""
    
    def test_make_safe_filename_basic(self):
        """Debe convertir caracteres especiales a guiones bajos"""
        assert make_safe_filename("Factura #123.pdf") == "Factura_123.pdf"
        assert make_safe_filename("test file (2).txt") == "test_file_2_.txt"
    
    def test_make_safe_filename_preserves_valid_chars(self):
        """Debe preservar caracteres válidos"""
        assert make_safe_filename("test-file_v2.pdf") == "test-file_v2.pdf"
    
    def test_make_safe_filename_truncates_long_names(self):
        """Debe truncar nombres muy largos"""
        long_name = "A" * 200 + ".pdf"
        result = make_safe_filename(long_name)
        assert len(result) == 128
    
    def test_make_safe_filename_custom_max_length(self):
        """Debe respetar longitud máxima personalizada"""
        long_name = "A" * 100
        result = make_safe_filename(long_name, max_length=50)
        assert len(result) == 50
    
    def test_make_safe_filename_strips_whitespace(self):
        """Debe eliminar espacios al inicio y final"""
        assert make_safe_filename("  test.pdf  ") == "test.pdf"

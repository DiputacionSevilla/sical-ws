# tests/test_config.py
"""
Tests unitarios para el módulo core.config
"""
import pytest
from unittest.mock import patch, MagicMock
from core.config import get_cfg


class TestGetCfg:
    """Tests para la función get_cfg"""
    
    @patch('os.getenv')
    def test_get_cfg_returns_env_value(self, mock_getenv):
        """Debe retornar el valor de la variable de entorno"""
        mock_getenv.return_value = "test_value"
        assert get_cfg("TEST_KEY") == "test_value"
        mock_getenv.assert_called_once_with("TEST_KEY", "")
    
    @patch('os.getenv')
    def test_get_cfg_returns_default_when_not_set(self, mock_getenv):
        """Debe retornar el valor por defecto si no existe la variable"""
        mock_getenv.return_value = None
        assert get_cfg("MISSING_KEY", "default") == "default"
    
    @patch('os.getenv')
    def test_get_cfg_empty_default(self, mock_getenv):
        """Debe retornar string vacío por defecto"""
        mock_getenv.return_value = None
        assert get_cfg("MISSING_KEY") == ""


# Nota: Los tests de conexión a Oracle requieren un entorno de prueba
# con base de datos Oracle configurada. Se pueden implementar usando
# mocks o una base de datos de prueba.

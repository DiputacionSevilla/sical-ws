# tests/test_session.py
"""
Tests unitarios para el módulo core.session
"""
import pytest
from core.session import AppSession


class TestAppSession:
    """Tests para la clase AppSession"""
    
    def test_session_initialization(self):
        """Debe inicializarse con valores por defecto"""
        session = AppSession()
        assert session.auth_ok is False
        assert session.db_target is None
        assert session.empresa is None
        assert session.usuario is None
        assert session.metadata == {}
    
    def test_set_authenticated(self):
        """Debe configurar correctamente la autenticación"""
        session = AppSession()
        session.set_authenticated("Empresa A", "SIDA", "usuario1")
        
        assert session.auth_ok is True
        assert session.empresa == "Empresa A"
        assert session.db_target == {"sid": "SIDA"}
        assert session.usuario == "usuario1"
    
    def test_is_authenticated(self):
        """Debe verificar correctamente el estado de autenticación"""
        session = AppSession()
        assert session.is_authenticated() is False
        
        session.set_authenticated("Empresa A", "SIDA")
        assert session.is_authenticated() is True
    
    def test_get_sid(self):
        """Debe retornar el SID correctamente"""
        session = AppSession()
        assert session.get_sid() is None
        
        session.set_authenticated("Empresa A", "SIDA")
        assert session.get_sid() == "SIDA"
    
    def test_reset(self):
        """Debe reiniciar la sesión correctamente"""
        session = AppSession()
        session.set_authenticated("Empresa A", "SIDA", "usuario1")
        session.set_metadata("key", "value")
        
        session.reset()
        
        assert session.auth_ok is False
        assert session.db_target is None
        assert session.empresa is None
        assert session.usuario is None
        assert session.metadata == {}
    
    def test_invalidate_if_changed(self):
        """Debe invalidar la sesión si el SID cambió"""
        session = AppSession()
        session.set_authenticated("Empresa A", "SIDA")
        
        # SID diferente - debe invalidar
        assert session.invalidate_if_changed("SIDB") is True
        assert session.is_authenticated() is False
        
        # Reautenticar
        session.set_authenticated("Empresa A", "SIDA")
        
        # Mismo SID - no debe invalidar
        assert session.invalidate_if_changed("SIDA") is False
        assert session.is_authenticated() is True
    
    def test_metadata_operations(self):
        """Debe manejar metadatos correctamente"""
        session = AppSession()
        
        # Set y get
        session.set_metadata("test_key", "test_value")
        assert session.get_metadata("test_key") == "test_value"
        
        # Get con default
        assert session.get_metadata("missing_key", "default") == "default"
        
        # Get sin default
        assert session.get_metadata("missing_key") is None

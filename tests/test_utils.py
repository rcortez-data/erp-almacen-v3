"""
Tests para funciones de utilidad.
"""

import pytest
from utils import (
    validar_cantidad, validar_email, formatear_cantidad,
    calcular_iva, calcular_importe, dividir_en_lotes
)


class TestValidacion:
    """Tests de funciones de validación."""
    
    def test_validar_cantidad_valida(self):
        """Cantidad válida se acepta."""
        valido, valor, msg = validar_cantidad("100.5")
        assert valido is True
        assert valor == 100.5
        assert msg == ""
    
    def test_validar_cantidad_negativa(self):
        """Cantidad negativa se rechaza."""
        valido, valor, msg = validar_cantidad("-10")
        assert valido is False
        assert "negativa" in msg.lower()
    
    def test_validar_email_valido(self):
        """Email válido se acepta."""
        assert validar_email("usuario@dominio.com") is True
    
    def test_validar_email_invalido(self):
        """Email inválido se rechaza."""
        assert validar_email("noesuneemail") is False


class TestCalculos:
    """Tests de funciones de cálculo."""
    
    def test_calcular_iva_defecto(self):
        """Cálculo de IVA con tasa default (16%)."""
        iva = calcular_iva(100.0)
        assert iva == 16.0
    
    def test_calcular_iva_diferente(self):
        """Cálculo de IVA con tasa personalizada."""
        iva = calcular_iva(100.0, tasa=0.10)
        assert iva == 10.0
    
    def test_calcular_importe(self):
        """Cálculo de importe (cantidad × precio)."""
        importe = calcular_importe(5, 10.5)
        assert importe == 52.5


class TestFormato:
    """Tests de funciones de formateo."""
    
    def test_formatear_cantidad_con_miles(self):
        """Formatea cantidad con separadores."""
        resultado = formatear_cantidad(1234567.89)
        assert "," in resultado
        assert "1,234,567.89" == resultado


class TestBatch:
    """Tests de procesamiento en lotes."""
    
    def test_dividir_en_lotes(self):
        """Divide lista en lotes correctamente."""
        lista = list(range(10))
        lotes = dividir_en_lotes(lista, 3)
        
        assert len(lotes) == 4
        assert len(lotes[0]) == 3
        assert len(lotes[-1]) == 1

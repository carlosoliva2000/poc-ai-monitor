"""Prueba mínima: el paquete del módulo de IA importa y ve los contratos."""

import ai_module
import poc_contracts


def test_imports() -> None:
    assert ai_module is not None
    assert poc_contracts is not None

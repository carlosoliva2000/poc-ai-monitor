"""Prueba mínima: el paquete de la plataforma importa y ve los contratos."""

import platform_app
import poc_contracts


def test_imports() -> None:
    assert platform_app is not None
    assert poc_contracts is not None

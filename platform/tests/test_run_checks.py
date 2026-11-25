"""Argumentos del comando de ejecución sin web (`platform_app.run`)."""

import pytest

from platform_app.run import Ask, ManualFault, _incident_line


def test_manual_fault_argument() -> None:
    assert ManualFault.parse("radar:mute:150:200") == ManualFault("radar", "mute", 150.0, 200.0)
    with pytest.raises(Exception, match="fuente:modo:inicio:fin"):
        ManualFault.parse("radar:150")


def test_ask_argument() -> None:
    assert Ask.parse("monitor:200:Why?") == Ask("monitor", 200.0, "Why?")
    assert Ask.parse("report:end:What?").when is None
    with pytest.raises(Exception, match="conversación:cuándo:texto"):
        Ask.parse("nobody:1:x")


def test_an_incident_revision_is_printed_in_one_line() -> None:
    event = {
        "payload": {
            "incident_id": "inc-0001", "change": "opened", "name": "GPS spoofing", "state": "open",
            "severity": "high", "confidence": "confirmed", "as_of_sim_time": 200.0,
        }
    }  # fmt: skip
    assert (
        _incident_line(event) == "T+03:20  opened   inc-0001 GPS spoofing · open · high · confirmed"
    )

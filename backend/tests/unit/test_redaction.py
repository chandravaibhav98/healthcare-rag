"""PHI redaction before persistence (ADR-0009)."""

from __future__ import annotations

import pytest

from app.core.redaction import redact


@pytest.mark.parametrize(
    ("text", "secret", "marker"),
    [
        ("Patient MRN 12345678 has a fever", "12345678", "[ID]"),
        ("medical record number: AB-99812 needs isolation?", "AB-99812", "[ID]"),
        ("SSN 123-45-6789", "123-45-6789", "[ID]"),
        ("born 03/04/1950, which vaccines?", "03/04/1950", "[DATE]"),
        ("DOB: 12 March 1961", "12 March 1961", "[DATE]"),
        ("visited on 2024-05-01", "2024-05-01", "[DATE]"),
        ("email jane.doe@nhs.net please", "jane.doe@nhs.net", "[EMAIL]"),
        ("call +44 20 7946 0958 now", "7946 0958", "[PHONE]"),
        ("Mr John Smith needs gloves", "John Smith", "[NAME]"),
        ("patient named Maria Lopez asks", "Maria Lopez", "[NAME]"),
        ("reference 123456789012345 flagged", "123456789012345", "[ID]"),
    ],
)
def test_identifiers_are_replaced(text: str, secret: str, marker: str) -> None:
    result = redact(text)
    assert secret not in result.text
    assert marker in result.text
    assert result.count >= 1


@pytest.mark.parametrize(
    "text",
    [
        "Store vaccines at 2-8 °C for 30 days.",
        "Rub hands for 20–30 seconds with 70% alcohol.",
        "Use 1,000 ppm chlorine; observe for 15 minutes.",
        "Give 2 doses 4 weeks apart.",
        "How long should hand hygiene take?",
    ],
)
def test_clinical_quantities_are_untouched(text: str) -> None:
    result = redact(text)
    assert result.text == text
    assert result.count == 0


def test_count_reflects_every_replacement() -> None:
    result = redact("Patient MRN 12345678 born 03/04/1950, email a@b.org")
    assert result.count == 3

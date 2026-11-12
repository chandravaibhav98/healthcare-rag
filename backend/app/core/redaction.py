"""PHI redaction before persistence (ADR-0009).

Questions can contain patient details even though the corpus is synthetic. Every
question is passed through these rules before it is written to `query_log`. The rules
are deliberately conservative (prefer over-redaction) and leave clinical quantities such
as "15 minutes", "2–8 °C", "70%" or "1,000 ppm" alone. Free-text names without a title
or "patient" prefix cannot be detected reliably by rules; that residual risk is why raw
question text is never logged in production and why `query_log` has a retention period.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

_MONTHS: Final = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_NAME: Final = r"[A-Z][a-z'\-]+(?:\s+[A-Z][a-z'\-]+){0,2}"

# Order matters: specific identifiers first, then generic number shapes.
_RULES: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("[EMAIL]", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    (
        "[ID]",
        re.compile(
            r"(?i)\b(?:mrn|medical\s+record(?:\s+(?:number|no\.?|#))?|patient\s+(?:id|number|no\.?)|"
            r"hospital\s+(?:number|no\.?)|nhs\s+(?:number|no\.?)|ssn)\s*[:#]?\s*[A-Z0-9][A-Z0-9-]{3,}"
        ),
    ),
    ("[ID]", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        "[DATE]",
        re.compile(
            r"(?i)\b(?:dob|date\s+of\s+birth|born(?:\s+on)?)\s*[:\-]?\s*"
            rf"(?:\d{{1,4}}[/.\-]\d{{1,2}}[/.\-]\d{{1,4}}|\d{{1,2}}\s+{_MONTHS}\.?\s+\d{{4}}|{_MONTHS}\.?\s+\d{{1,2}},?\s+\d{{4}})"
        ),
    ),
    ("[DATE]", re.compile(r"\b\d{1,2}[/.]\d{1,2}[/.](?:\d{4}|\d{2})\b")),
    ("[DATE]", re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")),
    ("[DATE]", re.compile(rf"(?i)\b\d{{1,2}}\s+{_MONTHS}\.?\s+(?:19|20)\d{{2}}\b")),
    ("[DATE]", re.compile(rf"(?i)\b{_MONTHS}\.?\s+\d{{1,2}},?\s+(?:19|20)\d{{2}}\b")),
    ("[PHONE]", re.compile(r"(?<![\w.])\+?\d(?:[\s().-]?\d){7,13}(?![\w.])")),
    ("[NAME]", re.compile(rf"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof)\.?\s+{_NAME}")),
    ("[NAME]", re.compile(rf"(?i:\bpatient(?:\s+(?:named|called))?)\s+{_NAME}(?=\s|[,.?!]|$)")),
)
#: Long digit runs that look like record numbers (7+ digits), checked last.
_LONG_NUMBER: Final = re.compile(r"(?<![\w.,])\d{7,}(?![\w.,])")


@dataclass(frozen=True, slots=True)
class Redaction:
    text: str
    count: int


def redact(text: str) -> Redaction:
    count = 0
    for placeholder, pattern in _RULES:
        text, n = pattern.subn(placeholder, text)
        count += n
    text, n = _LONG_NUMBER.subn("[ID]", text)
    return Redaction(text=text, count=count + n)

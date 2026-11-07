"""Answer-type cues: what kind of fact does the question ask for?

Classic extractive QA uses the expected answer type to prefer sentences that can
actually answer the question. A "how often" question wants a frequency, not merely a
sentence that repeats the question's nouns. The cues are fixed regular expressions:
deterministic, explainable and cheap. Each cue is
(name, question pattern, sentence pattern or None = list items).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

_FLAGS: Final = re.IGNORECASE

_UNIT_TIME: Final = r"(?:s|sec|seconds?|min|minutes?|h|hours?|days?|weeks?|months?|years?)"


@dataclass(frozen=True, slots=True)
class AnswerType:
    name: str
    question: re.Pattern[str]
    sentence: re.Pattern[str] | None  # None: list items (procedural steps) answer it


ANSWER_TYPES: Final = (
    AnswerType(
        "duration",
        re.compile(
            r"\bhow long\b|\bduration\b|\bhow many (?:seconds|minutes|hours|days)\b", _FLAGS
        ),
        re.compile(rf"\b\d+(?:[.,]\d+)?(?:\s*[–-]\s*\d+)?\s*{_UNIT_TIME}\b", _FLAGS),
    ),
    AnswerType(
        "frequency",
        re.compile(r"\bhow often\b|\bfrequen(?:cy|tly)\b|\bhow regularly\b", _FLAGS),
        re.compile(
            r"\b(?:annually|yearly|daily|weekly|monthly|quarterly|every|each (?:day|year|shift)"
            r"|twice|once|times (?:a|per)|per (?:day|week|shift))\b",
            _FLAGS,
        ),
    ),
    AnswerType(
        "temperature",
        re.compile(r"\btemperatures?\b|\bhow (?:cold|hot|warm)\b|\b°\s*c\b", _FLAGS),
        re.compile(r"°\s*C|\bdegrees\b", _FLAGS),
    ),
    AnswerType(
        "quantity",
        re.compile(
            r"\bhow many\b|\bhow much\b|\bpercent(?:age)?\b|\bconcentration\b|\bminimum\b", _FLAGS
        ),
        re.compile(r"\d"),
    ),
    AnswerType(
        "timing",
        re.compile(r"^\s*when\b|\bhow soon\b|\bhow quickly\b|\bdeadline\b", _FLAGS),
        re.compile(
            r"\b(?:within|before|after|immediately|as soon as|when|until|prior to|no later than)\b",
            _FLAGS,
        ),
    ),
    AnswerType(
        "procedure",
        re.compile(
            r"\b(?:order|sequence|steps?|procedure|how (?:do|should|to|must)\b.*\b(?:remove|put|"
            r"don|doff|perform|prepare|clean|dispose|report|respond))",
            _FLAGS,
        ),
        None,
    ),
)


def detect_answer_types(question: str) -> tuple[AnswerType, ...]:
    return tuple(t for t in ANSWER_TYPES if t.question.search(question))


def matches_answer_type(types: tuple[AnswerType, ...], text: str, *, is_list_item: bool) -> bool:
    return any(
        (t.sentence is None and is_list_item)
        or (t.sentence is not None and t.sentence.search(text))
        for t in types
    )

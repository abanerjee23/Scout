"""Bounded deterministic report intake. No model, write tools or relative-date guessing."""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApiInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class EmptyInput(ApiInput):
    pass


class PersonaInput(ApiInput):
    persona: Literal["employee", "manager"]


class ProposalInput(ApiInput):
    message: str = Field(min_length=1, max_length=2000)


class ReportHeader(ApiInput):
    name: str = Field(min_length=3, max_length=120)
    startDate: date
    endDate: date
    businessPurpose: str = Field(min_length=5, max_length=500)

    @field_validator("startDate", "endDate", mode="before")
    @classmethod
    def explicit_date(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Use YYYY-MM-DD with an explicit year")
        parsed = date.fromisoformat(value)
        if not 2000 <= parsed.year <= 2100:
            raise ValueError("Use a year between 2000 and 2100")
        return parsed

    @field_validator("name", "businessPurpose")
    @classmethod
    def readable_text(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("Use a single line of readable text")
        return value

    @model_validator(mode="after")
    def chronological(self):
        if self.endDate < self.startDate:
            raise ValueError("End date must not be before start date")
        return self


class ConfirmationInput(ApiInput):
    proposalToken: str = Field(min_length=20, max_length=1000)
    confirmed: Literal[True]
    header: ReportHeader

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit confirmation is required")
        return value


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
MONTH_PATTERN = "(?:" + "|".join(MONTHS) + ")"


def parse_report(message: str) -> dict:
    """Recognize explicit ISO or English date ranges; leave ambiguity for human review."""
    text = re.sub(r"[–—]", "-", message.strip())
    header = {"name": "", "startDate": "", "endDate": "", "businessPurpose": ""}
    problems: dict[str, str] = {}
    date_span: tuple[int, int] | None = None
    iso = list(re.finditer(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", text))
    shared = re.search(
        rf"\b(\d{{1,2}})\s*(?:-|to)\s*(\d{{1,2}})\s+({MONTH_PATTERN})\s+(\d{{4}})\b",
        text,
        re.I,
    )
    full = list(re.finditer(rf"\b(\d{{1,2}})\s+({MONTH_PATTERN})\s+(\d{{4}})\b", text, re.I))
    try:
        if len(iso) == 2 and not full:
            start, end = (date.fromisoformat(match.group()) for match in iso)
            date_span = (iso[0].start(), iso[1].end())
        elif not iso and shared and len(full) == 1:
            d1, d2, month, year = shared.groups()
            start = date(int(year), MONTHS[month.lower()], int(d1))
            end = date(int(year), MONTHS[month.lower()], int(d2))
            date_span = shared.span()
        elif not iso and len(full) == 2:
            dates = [date(int(m[3]), MONTHS[m[2].lower()], int(m[1])) for m in full]
            start, end = dates
            date_span = (full[0].start(), full[1].end())
        elif len(iso) == 1 and not full:
            start = end = date.fromisoformat(iso[0].group())
            date_span = iso[0].span()
            # Do not mistake a partially specified range for a one-day visit.
            if re.search(
                r"\b(?:to(?!\s+attend)|until|through)\b|\d\s*-\s*\d", text[iso[0].end() :]
            ):
                raise ValueError("Incomplete date range")
        elif not iso and len(full) == 1 and not shared:
            m = full[0]
            if re.search(rf"\b\d{{1,2}}\s+{MONTH_PATTERN}", text[: m.start()], re.I):
                raise ValueError("The other endpoint needs an explicit year")
            start = end = date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
            date_span = m.span()
            if re.search(r"\b(?:to(?!\s+attend)|until|through)\b", text[m.end() :]):
                raise ValueError("Incomplete date range")
        else:
            raise ValueError("Missing or ambiguous dates")
        # Every recognizable date signal must belong to the selected expression.
        # Unsupported/mixed formats are clarified rather than silently discarded.
        signals = re.finditer(
            rf"(?<!\d)\d{{4}}-\d{{1,2}}(?:-\d{{1,2}})?(?!\d)|"
            rf"\b\d{{1,2}}(?:\s*(?:-|to)\s*\d{{1,2}})?\s+{MONTH_PATTERN}"
            rf"(?:\s+\d{{4}})?\b|\b\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?\b|"
            r"\b(?:today|tomorrow|yesterday|next\s+(?:week|month|year))\b",
            text,
            re.I,
        )
        if any(m.start() < date_span[0] or m.end() > date_span[1] for m in signals):
            raise ValueError("Additional or incomplete date expression")
        if re.search(r"\b(?:to|until|through|or)\s*$", text[: date_span[0]], re.I):
            raise ValueError("Incomplete preceding endpoint")
        endpoints = iso if iso else full
        if len(endpoints) == 2 and not re.fullmatch(
            r"\s*(?:to|-|until|through)\s*",
            text[endpoints[0].end() : endpoints[1].start()],
            re.I,
        ):
            raise ValueError("Conflicting date endpoints")
        if not 2000 <= start.year <= 2100 or not 2000 <= end.year <= 2100 or end < start:
            raise ValueError("Invalid date range")
        header.update(startDate=start.isoformat(), endDate=end.isoformat())
    except ValueError:
        problems["dates"] = "Confirm both dates, including the year (YYYY-MM-DD)."

    purpose = re.search(r"\b(?:business purpose|purpose)\s*:\s*(.+?)(?:;|$)", text, re.I)
    if not purpose and date_span:
        purpose = re.search(r"\b(?:for|to attend)\s+(.+)$", text[date_span[1] :], re.I)
    if purpose:
        header["businessPurpose"] = purpose[1].strip().rstrip(".")
    if len(header["businessPurpose"]) < 5:
        problems["businessPurpose"] = "What is the business purpose of this report?"

    named = re.search(r"\b(?:report name|name)\s*:\s*(.+?)(?:;|$)", text, re.I)
    if named:
        header["name"] = named[1].strip()
    elif date_span:
        prefix = text[: date_span[0]].strip(" ,;:")
        prefix = re.sub(
            r"^(?:please\s+)?(?:prepare|create|start)\s+(?:my\s+|a\s+|an\s+)?",
            "",
            prefix,
            flags=re.I,
        )
        prefix = re.sub(r"\s+(?:for|from|on)$", "", prefix, flags=re.I)
        header["name"] = prefix[:120].strip()
    if len(header["name"]) < 3:
        problems["name"] = "What would you like to call this report?"
    if not problems:
        try:
            ReportHeader.model_validate(header)
        except ValueError:
            problems["header"] = "Review the report name, dates and business purpose."
    return {
        "header": header,
        "questions": list(problems.values()),
        "ready": not problems,
        "parser": "deterministic-v1",
    }

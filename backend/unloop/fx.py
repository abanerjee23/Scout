"""Fixed-host exact-date FX adapters; no prior-day substitution or float money."""

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from time import monotonic

import httpx
from iso4217 import Currency
from sqlalchemy import select

from unloop.models import FxObservation


class FxPending(Exception):
    pass


def currency(value):
    try:
        if value not in {item.code for item in Currency} or value in {"XXX", "XTS"}:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Unsupported ISO currency") from None
    return value


def positive(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result <= 0 or result > Decimal("1e12"):
            raise ValueError
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise FxPending("invalid_rate") from None


class HistoricalFx:
    def __init__(self, oxr_key=None):
        self.oxr_key = oxr_key

    @classmethod
    def from_env(cls, values):
        # Match the private example/doctor; keep existing deployments compatible.
        return cls(values.get("OPEN_EXCHANGE_RATES_APP_ID") or values.get("OXR_APP_ID"))

    def request(self, url, params=None):
        deadline = monotonic() + 10
        try:
            with httpx.Client(
                timeout=httpx.Timeout(5, connect=3), follow_redirects=False
            ) as client:
                with client.stream("GET", url, params=params) as response:
                    if response.status_code != 200:
                        raise FxPending("provider_unavailable")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        if monotonic() > deadline:
                            raise FxPending("provider_unavailable")
                        data.extend(chunk)
                        if len(data) > 128 * 1024:
                            raise FxPending("invalid_rate")
                    return json.loads(data, parse_float=Decimal, parse_int=Decimal)
        except (httpx.HTTPError, ValueError, TypeError):
            raise FxPending("provider_unavailable") from None

    def fetch(self, code, day):
        currency(code)
        if day > datetime.now(UTC).date():
            raise FxPending("unpublished_date")
        try:
            payload = self.request(
                f"https://api.frankfurter.dev/v2/providers/ecb/rate/{code.lower()}/gbp",
                {"date": day.isoformat()},
            )
            if (
                payload["date"] != day.isoformat()
                or payload["base"] != code
                or payload["quote"] != "GBP"
            ):
                raise FxPending("wrong_date_or_pair")
            return {
                "currency": code,
                "date": day.isoformat(),
                "provider": "ecb",
                "rate": str(positive(payload["rate"])),
                "source": "https://api.frankfurter.dev/v2/providers/ecb",
            }
        except (FxPending, KeyError, TypeError):
            if not self.oxr_key:
                raise FxPending("conversion_pending") from None
        try:
            payload = self.request(
                f"https://openexchangerates.org/api/historical/{day.isoformat()}.json",
                {"app_id": self.oxr_key},
            )
            observed = datetime.fromtimestamp(int(payload["timestamp"]), UTC).date()
            if observed != day or payload["base"] != "USD":
                raise FxPending("wrong_date_or_pair")
            base = Decimal(1) if code == "USD" else positive(payload["rates"][code])
            rate = positive(payload["rates"]["GBP"]) / base
            return {
                "currency": code,
                "date": day.isoformat(),
                "provider": "oxr",
                "rate": str(rate),
                "source": "https://openexchangerates.org/api/historical",
            }
        except (KeyError, TypeError, ValueError, OverflowError, OSError, FxPending):
            raise FxPending("conversion_pending") from None


def saved(db, code, day):
    if code == "GBP":
        return {
            "currency": "GBP",
            "date": day.isoformat(),
            "provider": "native",
            "rate": "1",
            "source": "GBP native",
        }
    rows = db.scalars(
        select(FxObservation).where(
            FxObservation.currency == code,
            FxObservation.rate_date == day,
            FxObservation.provider.in_(["ecb", "oxr"]),
        )
    ).all()
    for row in sorted(rows, key=lambda item: item.provider != "ecb"):
        try:
            rate = positive(row.rate)
        except FxPending:
            continue
        expected = (
            "https://api.frankfurter.dev/v2/providers/ecb"
            if row.provider == "ecb"
            else "https://openexchangerates.org/api/historical"
        )
        if row.source == expected:
            return {
                "currency": code,
                "date": day.isoformat(),
                "provider": row.provider,
                "rate": str(rate),
                "source": row.source,
            }
    return None


def validate_observation(observation, code, day):
    sources = {
        "ecb": "https://api.frankfurter.dev/v2/providers/ecb",
        "oxr": "https://openexchangerates.org/api/historical",
        "native": "GBP native",
    }
    try:
        provider = observation["provider"]
        if (
            observation["currency"] != code
            or observation["date"] != day.isoformat()
            or observation["source"] != sources[provider]
            or (provider == "native") != (code == "GBP")
        ):
            raise FxPending("invalid_rate")
        rate = positive(observation["rate"])
        if code == "GBP" and rate != 1:
            raise FxPending("invalid_rate")
        return {
            "currency": code,
            "date": day.isoformat(),
            "provider": provider,
            "source": sources[provider],
            "rate": str(rate),
        }
    except (KeyError, TypeError):
        raise FxPending("invalid_rate") from None

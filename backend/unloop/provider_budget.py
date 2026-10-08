"""Shared conservative reservations; failures do not refund uncertain provider spend."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from unloop.extraction import ExtractionFailure
from unloop.models import ModelBudget


def reserve(db, settings, owner_id=None):
    if settings is None:
        raise ExtractionFailure("model_unconfigured")
    amount = settings.reserve()
    scopes = [("global", settings.max_calls)]
    if owner_id is not None:
        scopes.append((str(owner_id), settings.session_calls))
    for key, ceiling in scopes:
        db.execute(
            insert(ModelBudget).values(key=key, calls=0, reserved_usd="0").on_conflict_do_nothing()
        )
        budget = db.scalar(select(ModelBudget).where(ModelBudget.key == key).with_for_update())
        if budget.calls >= ceiling or (
            key == "global" and Decimal(budget.reserved_usd) + amount > settings.budget_usd
        ):
            raise ExtractionFailure("budget_exhausted")
        budget.calls += 1
        budget.reserved_usd = str(Decimal(budget.reserved_usd) + amount)
    return amount

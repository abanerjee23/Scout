"""Dedicated deterministic browser server: real HTTP/PostgreSQL, explicitly fake A1/FX.

This file is excluded from the production image and is never an application flag.
"""

import os
import sys
from pathlib import Path
from threading import Event, Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from postgres_test_support import isolated_database, isolated_schema
from sqlalchemy import text
from unloop import create_app
from unloop.expense_worker import run_expense_once
from unloop.policy_index import build_index
from unloop.policy_questions import run_question_once
from unloop.worker import run_once

from backend.tests.test_categories import AIR, CategoryExtractor
from backend.tests.test_meals import TEST_LIMITS, TEST_POLICY, FakeExtractor
from backend.tests.test_policy_questions import FakeAnswerer, FakeEmbedder


class SyntheticFx:
    def fetch(self, code, day):
        return {
            "currency": code,
            "date": day.isoformat(),
            "provider": "ecb",
            "rate": "0.8",
            "source": "https://api.frankfurter.dev/v2/providers/ecb",
        }


def main():
    if not os.environ.get("TEST_DATABASE_URL"):
        raise RuntimeError("Explicit test database required")
    with isolated_database(os.environ["TEST_DATABASE_URL"]) as (url, engine):
        app = create_app(
            {
                "DATABASE_URL": url,
                "UNLOOP_TEST_SCHEMA": isolated_schema(engine),
                "APP_ORIGIN": "http://127.0.0.1:5174",
                "SESSION_COOKIE_SECURE": "false",
            }
        )
        app.state.a1_settings = TEST_LIMITS
        app.state.meal_policy = TEST_POLICY
        app.state.policy_qa_enabled = True
        with engine.begin() as db:
            db.execute(
                text(
                    f'CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA "{isolated_schema(engine)}"'
                )
            )
        build_index(engine, TEST_POLICY, TEST_LIMITS, FakeEmbedder())

        class RoutedExtractor:
            def extract(self, context, documents):
                adapter = (
                    CategoryExtractor(AIR)
                    if context.get("categoryOverride") == "air"
                    else FakeExtractor({"mealType": None})
                )
                return adapter.extract(context, documents)

        stop = Event()

        def worker():
            while not stop.is_set():
                run_once(engine)
                run_expense_once(
                    engine,
                    TEST_LIMITS,
                    RoutedExtractor(),
                    TEST_POLICY,
                    SyntheticFx(),
                )
                run_question_once(engine, TEST_LIMITS, FakeAnswerer(), FakeEmbedder())
                stop.wait(0.2)

        thread = Thread(target=worker, daemon=True)
        thread.start()
        try:
            uvicorn.run(app, host="127.0.0.1", port=5002, log_level="warning", access_log=False)
        finally:
            stop.set()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()

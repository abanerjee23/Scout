"""Approved clause ingestion and exact pgvector search; index data is never policy authority."""

import hashlib
import json
import math
import re
from time import monotonic

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from unloop.models import PolicyChunk
from unloop.observability import observe
from unloop.policy_registry import CHECKLISTS, store_policy
from unloop.provider_budget import reserve

EMBED_MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
CONFIG_ID = "text-embedding-3-small:1536:clauses-v1"


class GuidanceUnavailable(Exception):
    pass


def vector(values):
    if (
        len(values) != DIMENSIONS
        or any(type(value) not in (int, float) or not math.isfinite(value) for value in values)
        or not any(values)
    ):
        raise GuidanceUnavailable("invalid_embedding")
    return json.dumps(values, separators=(",", ":"))


class OpenAIEmbedder:
    def __init__(self, settings):
        self.settings = settings

    def embed(self, texts):
        from openai import OpenAI

        if (
            not texts
            or any(not value or len(value) > 8000 for value in texts)
            or sum(len(value.encode()) for value in texts) > self.settings.input_tokens
        ):
            raise GuidanceUnavailable("embedding_input_limit")
        started = monotonic()
        try:
            with OpenAI(
                api_key=self.settings.key,
                timeout=10,
                max_retries=0,
                base_url="https://api.openai.com/v1",
            ) as client:
                result = client.embeddings.create(
                    model=EMBED_MODEL, dimensions=DIMENSIONS, input=texts, encoding_format="float"
                )
                ordered = sorted(result.data, key=lambda value: value.index)
                if [value.index for value in ordered] != list(range(len(texts))):
                    raise GuidanceUnavailable("invalid_embedding")
                for value in ordered:
                    vector(value.embedding)
                observe(
                    {
                        "model": EMBED_MODEL,
                        "schemaVersion": "embeddings-1",
                        "latencyMs": int((monotonic() - started) * 1000),
                        "inputTokens": result.usage.prompt_tokens,
                        "outputTokens": 0,
                        "outcome": "embedded",
                    },
                    operation="embedding",
                )
                return [value.embedding for value in ordered]
        except Exception:
            observe(
                {"model": EMBED_MODEL, "outcome": "embedding_unavailable"}, operation="embedding"
            )
            raise GuidanceUnavailable("embedding_unavailable") from None


def extension_schema(db):
    namespace = db.scalar(
        text(
            "SELECT n.nspname FROM pg_extension e "
            "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector'"
        )
    )
    if namespace is None or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", namespace):
        raise GuidanceUnavailable("vector_unavailable")
    return namespace


def index_complete(db, source):
    rows = db.scalars(
        select(PolicyChunk).where(
            PolicyChunk.policy_version == source["version"],
            PolicyChunk.config_id == CONFIG_ID,
            PolicyChunk.source_hash == source["sourceHash"],
        )
    ).all()
    expected = {value["id"]: value for value in source["clauses"]}
    return len(rows) == len(expected) and all(
        row.clause_id in expected
        and row.text_hash == hashlib.sha256(expected[row.clause_id]["text"].encode()).hexdigest()
        for row in rows
    )


def build_index(engine, policy, settings, embedder):
    # No lock or DB transaction remains open while sending approved text to the provider.
    with Session(engine) as db, db.begin():
        source = store_policy(db, policy)
        extension_schema(db)
        if index_complete(db, source):
            return {
                "state": "already_indexed",
                "count": len(source["clauses"]),
                "configId": CONFIG_ID,
            }
        reserve(db, settings)
    texts = [value["title"] + "\n" + value["text"] for value in source["clauses"]]
    embeddings = embedder.embed(texts)
    if len(embeddings) != len(texts):
        raise GuidanceUnavailable("invalid_embedding")
    encoded = [vector(value) for value in embeddings]
    from sqlalchemy.dialects.postgresql import insert

    with Session(engine) as db, db.begin():
        for clause, embedding in zip(source["clauses"], encoded, strict=True):
            db.execute(
                insert(PolicyChunk)
                .values(
                    policy_version=source["version"],
                    config_id=CONFIG_ID,
                    clause_id=clause["id"],
                    source_hash=source["sourceHash"],
                    text_hash=hashlib.sha256(clause["text"].encode()).hexdigest(),
                    embedding=embedding,
                )
                .on_conflict_do_nothing()
            )
        if not index_complete(db, source):
            raise GuidanceUnavailable("index_version_mismatch")
    return {
        "state": "indexed",
        "count": len(texts),
        "configId": CONFIG_ID,
        "provider": EMBED_MODEL,
        "quality": "unmeasured",
    }


def retrieve(db, source, query_vector, question, *, category=None, mode="rag"):
    if mode == "fullContext":
        return source["clauses"]
    namespace = extension_schema(db)
    if not index_complete(db, source):
        raise GuidanceUnavailable("index_unavailable")
    # Names come only from verified pg_extension metadata. All user/vector/version values bind.
    nearest = db.scalars(
        text(
            "SELECT clause_id FROM policy_chunks WHERE policy_version = :version "
            "AND config_id = :config AND source_hash = :source "
            f'ORDER BY embedding::"{namespace}".vector OPERATOR("{namespace}".<=>) '
            f'CAST(:query AS "{namespace}".vector), clause_id LIMIT 5'
        ),
        {
            "version": source["version"],
            "config": CONFIG_ID,
            "source": source["sourceHash"],
            "query": vector(query_vector),
        },
    ).all()
    # Required restrictions bypass retrieval. Index corruption cannot introduce a new passage.
    required = set(
        CHECKLISTS.get(
            category,
            [
                "GEN-01",
                "GEN-02",
                "GEN-03",
                "GEN-05",
                "AIR-02",
                "AIR-03",
                "AIR-04",
                "AIR-05",
                "MEAL-03",
                "MEAL-04",
                "MEAL-05",
                "MEAL-06",
                "CUR-03",
            ],
        )
    )
    ids = (
        required
        | set(nearest)
        | {value["id"] for value in source["clauses"] if value["id"].lower() in question.lower()}
    )
    return [value for value in source["clauses"] if value["id"] in ids]


def main():
    import os

    from unloop.database import Settings, postgres_engine
    from unloop.extraction import A1Settings
    from unloop.meal_policy import MealPolicy

    settings = Settings.load()
    policy, limits = MealPolicy.load(os.environ), A1Settings.load(os.environ)
    if policy is None or limits is None or os.environ.get("POLICY_QA_ENABLED") != "true":
        raise SystemExit(
            "Policy indexing is disabled until approval and private budgets are configured."
        )
    engine = postgres_engine(
        settings.database_url, schema=settings.database_schema, production=settings.production
    )
    try:
        print(build_index(engine, policy, limits, OpenAIEmbedder(limits)))
    except Exception:
        raise SystemExit(
            "Policy indexing stopped; verify private provider/index configuration."
        ) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

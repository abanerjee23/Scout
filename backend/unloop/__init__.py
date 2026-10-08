"""FastAPI factory; no provider integration or automatic schema creation."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from unloop.api import ApiProblem, router
from unloop.database import Settings, postgres_engine
from unloop.evidence import UploadBodyLimit
from unloop.evidence import router as evidence_router
from unloop.evidence_validation import MAX_REQUEST_BYTES
from unloop.expenses import router as expense_router
from unloop.extraction import A1Settings
from unloop.gmail import router as gmail_router
from unloop.gmail_provider import GmailFailure, GmailSettings, GoogleAdapter
from unloop.meal_policy import MealPolicy
from unloop.policy_questions import router as policy_question_router
from unloop.policy_registry import router as policy_router


def create_app(test_config: dict | None = None) -> FastAPI:
    settings = Settings.load(test_config)
    engine = (
        postgres_engine(
            settings.database_url, schema=settings.database_schema, production=settings.production
        )
        if settings.database_url
        else None
    )

    @asynccontextmanager
    async def lifespan(_app):
        yield
        if engine is not None:
            engine.dispose()

    app = FastAPI(title="Unloop", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings, app.state.engine = settings, engine
    values = {**os.environ, **(test_config or {})}
    app.state.a1_settings = A1Settings.load(values)
    app.state.policy_qa_enabled = values.get("POLICY_QA_ENABLED") == "true"
    app.state.meal_policy = MealPolicy.load(values)
    app.state.gmail_settings = GmailSettings.load(
        {**os.environ, **(test_config or {})}, settings.app_origin
    )
    app.state.gmail_adapter = (
        GoogleAdapter(app.state.gmail_settings) if app.state.gmail_settings else None
    )

    @app.exception_handler(ApiProblem)
    async def problem_handler(_request: Request, exc: ApiProblem):
        response = JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
        )
        if exc.clear_cookie:
            response.delete_cookie(
                settings.cookie_name, httponly=True, secure=settings.cookie_secure, samesite="lax"
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(_request: Request, exc: RequestValidationError):
        # Never echo input/cookies/configuration into an error or log.
        fields = [
            {"field": ".".join(map(str, error["loc"][1:])), "message": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            {
                "error": {"code": "invalid_input", "message": "Review the highlighted fields."},
                "fields": fields,
            },
            status_code=422,
        )

    @app.exception_handler(GmailFailure)
    async def gmail_problem(_request: Request, exc: GmailFailure):
        return JSONResponse(
            {
                "error": {
                    "code": exc.code,
                    "message": "Gmail stopped. Review consent or reconnect. Evidence is retained.",
                }
            },
            status_code=409,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable(_request: Request, _exc: SQLAlchemyError):
        return JSONResponse(
            {
                "error": {
                    "code": "database_unavailable",
                    "message": "Report storage is unavailable. Retry after it is restored.",
                }
            },
            status_code=503,
        )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return JSONResponse(
            {"error": {"code": "not_found", "message": "Not found"}}, status_code=exc.status_code
        )

    app.add_middleware(UploadBodyLimit, limit=lambda: MAX_REQUEST_BYTES)
    # Sync SQL dependencies hold connections until their handler/commit completes.
    # Bound admissions below the pool (5 + 10 overflow) and AnyIO's thread budget.
    # Otherwise waiting dependencies can starve the handlers that release connections.
    admissions = asyncio.Semaphore(8)

    @app.middleware("http")
    async def database_admission(request: Request, call_next):
        if not request.url.path.startswith(("/api/", "/auth/")):
            return await call_next(request)
        try:
            await asyncio.wait_for(admissions.acquire(), timeout=5)
        except TimeoutError:
            return JSONResponse(
                {
                    "error": {
                        "code": "workspace_busy",
                        "message": "The workspace is busy. Retry shortly; saved data is retained.",
                    }
                },
                status_code=503,
                headers={"Retry-After": "2", "Cache-Control": "no-store"},
            )
        try:
            return await call_next(request)
        finally:
            admissions.release()

    @app.middleware("http")
    async def request_boundary(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in {
            "POST",
            "PATCH",
            "PUT",
            "DELETE",
        }:
            if (
                request.headers.get("origin") != settings.app_origin
                or request.headers.get("sec-fetch-site") == "cross-site"
            ):
                return JSONResponse(
                    {
                        "error": {
                            "code": "cross_site_request",
                            "message": "Use this app to make changes.",
                        }
                    },
                    status_code=403,
                )
            upload = (
                request.method == "POST"
                and request.url.path.startswith("/api/reports/")
                and request.url.path.endswith("/evidence")
            )
            expected_type = "multipart/form-data" if upload else "application/json"
            if request.headers.get("content-type", "").split(";")[0] != expected_type:
                return JSONResponse(
                    {
                        "error": {
                            "code": "multipart_required" if upload else "json_required",
                            "message": "Multipart form data is required."
                            if upload
                            else "JSON is required.",
                        }
                    },
                    status_code=415,
                )
            length = request.headers.get("content-length", "")
            if not length.isdigit() or int(length) > (MAX_REQUEST_BYTES if upload else 16 * 1024):
                return JSONResponse(
                    {
                        "error": {
                            "code": "request_too_large",
                            "message": "Request exceeds the upload or report-detail limit.",
                        }
                    },
                    status_code=413,
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = (
            "no-referrer"
            if request.url.path == "/auth/google/callback"
            else response.headers.get("Referrer-Policy", "same-origin")
        )
        return response

    app.include_router(router)
    app.include_router(evidence_router)
    app.include_router(gmail_router)
    app.include_router(expense_router)
    app.include_router(policy_router)
    app.include_router(policy_question_router)
    static = os.environ.get("UNLOOP_STATIC_DIR")
    if static:
        root = Path(static).resolve()
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(root / "index.html")

    return app

"""FastAPI factory; no provider integration or automatic schema creation."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from unloop.api import ApiProblem, router
from unloop.database import Settings, postgres_engine


def create_app(test_config: dict | None = None) -> FastAPI:
    settings = Settings.load(test_config)
    engine = (
        postgres_engine(settings.database_url, schema=settings.database_schema)
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
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse(
                    {"error": {"code": "json_required", "message": "JSON is required."}},
                    status_code=415,
                )
            length = request.headers.get("content-length", "")
            if not length.isdigit() or int(length) > 16 * 1024:
                return JSONResponse(
                    {
                        "error": {
                            "code": "request_too_large",
                            "message": "Keep report details under 16 KiB.",
                        }
                    },
                    status_code=413,
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    app.include_router(router)
    return app

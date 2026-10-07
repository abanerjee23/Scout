"""Flask application factory. Phase 0 exposes health only."""

from flask import Flask, jsonify


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=10 * 1024 * 1024)
    if test_config:
        app.config.update(test_config)

    @app.get("/api/health")
    def health():
        # Liveness is deliberately distinct from database/provider readiness.
        return jsonify(service="unloop", status="ok", phase="scaffold", persistence=False)

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(error="Not found"), 404

    return app

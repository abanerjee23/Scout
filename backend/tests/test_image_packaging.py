"""Railway production recipe and derived Cloud verification keep trust separate."""

from pathlib import Path

import pytest

from scripts.cloud_verify_image import verification_recipe


def test_production_recipe_is_portable_and_cloud_recipe_is_derived():
    recipe = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text()
    assert "--mount=" not in recipe
    assert "proxy_ca" not in recipe and "proxy_bundle" not in recipe
    assert "RUN npm ci --strict-ssl=true" in recipe
    assert "RUN uv sync --frozen --no-dev" in recipe
    temporary = verification_recipe(recipe)
    assert temporary.count("--mount=type=secret") == 2
    assert "required=true" in temporary
    assert "strict-ssl=false" not in temporary
    assert "COPY --from=frontend /build/dist" in temporary
    with pytest.raises(ValueError):
        verification_recipe(recipe.replace("npm ci", "npm install"))

"""Build the production Dockerfile with temporary managed-Cloud CA mounts only.

Railway uses the root Dockerfile unchanged. This wrapper derives a temporary
verification recipe; neither CA bytes nor Cloud paths enter the production recipe.
"""

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verification_recipe(source):
    replacements = {
        "RUN npm ci --strict-ssl=true": (
            "RUN --mount=type=secret,id=proxy_ca,required=true "
            "NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca npm ci --strict-ssl=true"
        ),
        "RUN uv sync --frozen --no-dev": (
            "RUN --mount=type=secret,id=proxy_bundle,required=true "
            "SSL_CERT_FILE=/run/secrets/proxy_bundle uv sync --frozen --no-dev"
        ),
    }
    for original, temporary in replacements.items():
        if source.count(original) != 1:
            raise ValueError("Production install steps changed; review the verification wrapper")
        source = source.replace(original, temporary)
    return source


def main():
    ca = os.environ.get("CODEX_PROXY_CERT")
    if not ca or not Path(ca).is_file():
        raise SystemExit("Managed Cloud CA unavailable; no TLS bypass attempted")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_TLS",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        }
    }
    with tempfile.TemporaryDirectory(prefix="unloop-image-verification-") as directory:
        recipe = Path(directory) / "Dockerfile"
        recipe.write_text(verification_recipe((ROOT / "Dockerfile").read_text()))
        subprocess.run(
            [
                "docker",
                "--host=unix:///var/run/docker.sock",
                "build",
                "--file",
                str(recipe),
                "--secret",
                f"id=proxy_ca,src={ca}",
                "--secret",
                "id=proxy_bundle,src=/etc/ssl/certs/ca-certificates.crt",
                "--tag",
                "unloop-phase1c:test",
                str(ROOT),
            ],
            env=environment,
            check=True,
            timeout=600,
        )


if __name__ == "__main__":
    main()

"""Fixtures for tests that need a real local Supabase stack (Docker)."""

import json
import subprocess
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session")
def supabase_env() -> Iterator[dict[str, str]]:
    """Reads the running local stack's API URL and anon key.

    Skips (does not fail) when the Supabase CLI or Docker aren't available, so the
    normal test run — which never selects the ``supabase`` marker — is unaffected,
    and a manual ``pytest -m supabase`` run degrades to a clear skip instead of a
    confusing connection error.
    """
    try:
        result = subprocess.run(
            ["supabase", "status", "-o", "json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"local Supabase stack is not running: {exc}")

    status = json.loads(result.stdout)
    yield {"url": status["API_URL"], "anon_key": status["ANON_KEY"]}

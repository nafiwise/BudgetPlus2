import pytest


@pytest.fixture(autouse=True)
def isolate_lithic_configuration(monkeypatch):
    """A developer's live .env must never enable external calls in unrelated tests."""
    monkeypatch.delenv('LITHIC_API_KEY', raising=False)
    monkeypatch.delenv('PUBLIC_BACKEND_URL', raising=False)
    monkeypatch.setenv('LITHIC_ENV', 'sandbox')

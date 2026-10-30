import pytest
from fastapi.testclient import TestClient
import main


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(main, "ROLE", "frontend")
    return main


def test_health_and_readiness(service):
    client = TestClient(service.app)
    assert client.get("/healthz").json() == {"status": "ok", "service": "frontend"}
    assert client.get("/readyz").json() == {"status": "ready", "service": "frontend"}
    assert "shop_http_requests_total" in client.get("/metrics").text


def test_platform_config_does_not_expose_secret(service, monkeypatch):
    monkeypatch.setattr(service, "ROLE", "payment")
    monkeypatch.setenv("APP_MESSAGE", "configured")
    monkeypatch.setenv("PAYMENT_DEMO_KEY", "private-demo-value")
    response = TestClient(service.app).get("/platform")
    assert response.json() == {
        "service": "payment",
        "message": "configured",
        "payment_secret_configured": True,
    }
    assert "private-demo-value" not in response.text


def test_frontend_forwards_demo_switches(service, monkeypatch):
    calls = []

    def fake_call(name, path="/", params=None):
        calls.append((name, params))
        return {"ok": True}

    monkeypatch.setattr(service, "call_service", fake_call)
    response = TestClient(service.app).get("/?fail=payment&slow=payment")
    assert response.status_code == 200
    assert calls == [("checkout", {"fail": "payment", "slow": "payment"})]


def test_checkout_calls_both_dependencies(service, monkeypatch):
    monkeypatch.setattr(service, "ROLE", "checkout")
    calls = []

    def fake_call(name, path="/", params=None):
        calls.append((name, params))
        return {"ok": True}

    monkeypatch.setattr(service, "call_service", fake_call)
    response = TestClient(service.app).get("/?fail=payment")
    assert response.status_code == 200
    assert calls == [("inventory", None), ("payment", {"fail": "payment"})]


def test_payment_failure_is_visible(service, monkeypatch):
    monkeypatch.setattr(service, "ROLE", "payment")
    response = TestClient(service.app).get("/?fail=payment")
    assert response.status_code == 503
    assert response.json()["detail"] == "Simulated payment failure"

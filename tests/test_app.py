from __future__ import annotations

from pdcscavengerhunt.app import create_app
from pdcscavengerhunt.settings import Settings


async def test_api_responses_are_not_cached(app):
    _request, response = await app.asgi_client.get("/api/health")

    assert response.status == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


async def test_production_responses_include_transport_and_content_security():
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://test:test@localhost/test",
        public_base_url="https://hunt.example.org/",
        session_secret="production-session-secret-that-is-long-enough",
        clue_code_secret="production-clue-secret-that-is-long-enough",
        secure_cookies=True,
        frontend_dist="/tmp/pdcscavengerhunt-missing-frontend",
    )
    app = create_app(settings, name="PDCScavengerHuntProductionHeadersTest")

    _request, response = await app.asgi_client.get("/api/health")

    assert response.status == 200
    assert settings.public_base_url == "https://hunt.example.org"
    assert response.headers["strict-transport-security"].startswith("max-age=")
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert (
        "frame-src 'self' https://*.cloudflarestream.com "
        "https://*.videodelivery.net"
        in response.headers["content-security-policy"]
    )

    _request, media_response = await app.asgi_client.get(
        "/api/v1/media/00000000-0000-0000-0000-000000000000"
    )
    assert media_response.headers["x-frame-options"] == "SAMEORIGIN"
    assert (
        "frame-ancestors 'self'"
        in media_response.headers["content-security-policy"]
    )


def test_stream_customer_code_is_normalized_to_a_subdomain():
    settings = Settings(
        cloudflare_stream_customer_subdomain="fo4vcqkfd42ymmwp",
    )

    assert settings.cloudflare_stream_customer_subdomain == (
        "customer-fo4vcqkfd42ymmwp.cloudflarestream.com"
    )

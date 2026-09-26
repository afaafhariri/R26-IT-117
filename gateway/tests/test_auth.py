"""Sign-up, confirmation, login, sessions and password reset, against a real
Postgres schema (see conftest.database_url)."""

import asyncio
import hashlib

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.maintenance import cleanup_expired
from app.models import Base
from tests.conftest import APP_URL

EMAIL = "ana@example.com"
PASSWORD = "correct horse battery"
COOKIE = "__Host-session"


def signup(h, email=EMAIL, password=PASSWORD):
    return h.client.post("/api/auth/signup", json={"email": email, "password": password})


def login(h, email=EMAIL, password=PASSWORD, remember_me=False):
    return h.client.post(
        "/api/auth/login", json={"email": email, "password": password, "remember_me": remember_me}
    )


def verify(h, token, password=PASSWORD):
    return h.client.post("/api/auth/verify-email", json={"token": token, "password": password})


def forgot(h, email=EMAIL):
    return h.client.post("/api/auth/password/forgot", json={"email": email})


def reset(h, token, password):
    return h.client.post("/api/auth/password/reset", json={"token": token, "password": password})


def signed_up_and_confirmed(h):
    signup(h)
    assert verify(h, h.email.link_token()).status_code == 200


def count(h, table):
    return h.sql(f"SELECT count(*) FROM {table}")[0][0]


# ── Sign-up and confirmation ─────────────────────────────────────────────────


def test_signup_emails_a_confirmation_link(harness):
    r = signup(harness)

    assert r.status_code == 202
    assert r.json() == {"message": "Check your email for a link to finish signing up."}
    assert "set-cookie" not in r.headers
    [mail] = harness.email.sent
    assert mail.to == EMAIL
    assert f"{APP_URL}/verify-email#token=" in mail.text


def test_passwords_are_stored_as_argon2id_hashes(harness):
    signup(harness)
    [(stored,)] = harness.sql("SELECT password_hash FROM users")
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


def test_signup_rejects_a_short_password(harness):
    r = signup(harness, password="too short")
    assert r.status_code == 422
    assert r.json() == {"detail": "Use at least 12 characters."}
    assert harness.email.sent == []


def test_signup_with_a_taken_email_looks_identical(harness):
    first = signup(harness)
    second = signup(harness, email="ANA@Example.com", password="some other long password")

    assert (second.status_code, second.json()) == (first.status_code, first.json())
    assert count(harness, "users") == 1
    assert harness.email.sent[-1].subject.startswith("You already have")


def test_confirming_needs_the_link_and_the_password_and_signs_in(harness):
    signup(harness)
    token = harness.email.link_token()

    assert verify(harness, token, password="not the password").status_code == 401
    r = verify(harness, token)
    assert r.status_code == 200
    assert r.json()["email_verified"] is True
    assert harness.client.get("/api/auth/me").json()["email"] == EMAIL
    assert verify(harness, token).status_code == 400  # single use


def test_a_newer_link_replaces_the_older_one(harness):
    signup(harness)
    older = harness.email.link_token()
    harness.client.post("/api/auth/verify-email/resend", json={"email": EMAIL})
    newer = harness.email.link_token()

    assert verify(harness, older).status_code == 400
    assert verify(harness, newer).status_code == 200


def test_someone_who_signs_up_with_your_email_first_cannot_take_the_account(harness):
    squatter_password = "the squatter's password"
    signup(harness, password=squatter_password)
    squatter_link = harness.email.link_token()

    # The real owner signs up; their password is not applied to the account.
    signup(harness, password=PASSWORD)
    assert harness.email.sent[-1].subject.startswith("You already have")
    # Opening the squatter's link with the owner's password activates nothing...
    assert verify(harness, squatter_link).status_code == 401
    # ...and the reset the email offers makes the account theirs.
    forgot(harness)
    assert reset(harness, harness.email.link_token(), PASSWORD).status_code == 200
    assert login(harness).status_code == 200
    assert login(harness, password=squatter_password).status_code == 401


# ── Login and sessions ───────────────────────────────────────────────────────


def test_login_is_refused_until_the_email_is_confirmed(harness):
    signup(harness)
    r = login(harness)
    assert r.status_code == 403
    assert "set-cookie" not in r.headers


def test_wrong_password_and_unknown_email_look_identical(harness):
    signed_up_and_confirmed(harness)
    wrong_password = login(harness, password="wrong password here")
    unknown_email = login(harness, email="nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": "Incorrect email or password."}


def test_session_cookie_is_locked_down(harness):
    signed_up_and_confirmed(harness)
    cookie = login(harness).headers["set-cookie"].lower()

    assert cookie.startswith(COOKIE.lower() + "=")
    for attribute in ("httponly", "secure", "path=/", "samesite=lax"):
        assert attribute in cookie
    assert "domain" not in cookie
    assert "max-age" not in cookie  # gone when the browser closes


def test_remember_me_keeps_the_cookie_for_30_days(harness):
    signed_up_and_confirmed(harness)
    cookie = login(harness, remember_me=True).headers["set-cookie"]
    assert "Max-Age=2592000" in cookie


def test_only_a_hash_of_the_session_id_is_stored(harness):
    signed_up_and_confirmed(harness)
    raw = harness.client.cookies.get(COOKIE)
    [(stored,)] = harness.sql("SELECT id_hash FROM sessions")
    assert stored == hashlib.sha256(raw.encode()).hexdigest() != raw


def test_logging_in_replaces_the_session_the_browser_already_had(harness):
    signed_up_and_confirmed(harness)
    before = harness.client.cookies.get(COOKIE)
    login(harness)

    assert harness.client.cookies.get(COOKIE) != before
    assert count(harness, "sessions") == 1


def test_logout_ends_the_session_on_the_server(harness):
    signed_up_and_confirmed(harness)
    raw = harness.client.cookies.get(COOKIE)

    assert harness.client.post("/api/auth/logout").status_code == 204
    assert count(harness, "sessions") == 0
    # A copy of the old cookie is useless.
    harness.client.cookies.set(COOKIE, raw, domain="testserver")
    assert harness.client.get("/api/auth/me").status_code == 401


def test_session_ends_after_idle_timeout(harness):
    signed_up_and_confirmed(harness)
    harness.sql("UPDATE sessions SET idle_expires_at = now() - interval '1 second'")

    assert harness.client.get("/api/auth/me").status_code == 401
    assert count(harness, "sessions") == 0


def test_session_ends_at_absolute_timeout_however_active(harness):
    signed_up_and_confirmed(harness)
    harness.sql("UPDATE sessions SET absolute_expires_at = now() - interval '1 second'")
    assert harness.client.get("/api/auth/me").status_code == 401


def test_activity_extends_the_idle_timeout_but_never_past_the_absolute_one(harness):
    signed_up_and_confirmed(harness)
    harness.sql(
        "UPDATE sessions SET last_seen_at = now() - interval '5 minutes',"
        " idle_expires_at = now() + interval '10 minutes'"
    )
    harness.client.get("/api/auth/me")
    [(extended,)] = harness.sql(
        "SELECT idle_expires_at > now() + interval '119 minutes' FROM sessions"
    )
    assert extended

    harness.sql(
        "UPDATE sessions SET last_seen_at = now() - interval '5 minutes',"
        " absolute_expires_at = now() + interval '30 minutes'"
    )
    harness.client.get("/api/auth/me")
    [(capped,)] = harness.sql("SELECT idle_expires_at = absolute_expires_at FROM sessions")
    assert capped


# ── Password reset ───────────────────────────────────────────────────────────


def test_password_reset_signs_out_everywhere(harness):
    signed_up_and_confirmed(harness)
    assert forgot(harness).status_code == 202
    assert "/reset-password#token=" in harness.email.sent[-1].text
    token = harness.email.link_token()

    assert reset(harness, token, "a brand new password").status_code == 200
    assert count(harness, "sessions") == 0
    assert harness.client.cookies.get(COOKIE) is None
    assert harness.email.sent[-1].subject.endswith("password was changed")
    assert login(harness).status_code == 401
    assert login(harness, password="a brand new password").status_code == 200
    assert reset(harness, token, "yet another password").status_code == 400


def test_a_rejected_new_password_does_not_use_up_the_link(harness):
    signed_up_and_confirmed(harness)
    forgot(harness)
    token = harness.email.link_token()

    assert reset(harness, token, "short").status_code == 422
    assert reset(harness, token, "a brand new password").status_code == 200


def test_expired_reset_link_is_rejected(harness):
    signed_up_and_confirmed(harness)
    forgot(harness)
    harness.sql("UPDATE email_tokens SET expires_at = now() - interval '1 second'")
    assert reset(harness, harness.email.link_token(), "a brand new password").status_code == 400


def test_forgot_password_for_an_unknown_email_looks_identical(harness):
    signed_up_and_confirmed(harness)
    sent_before = len(harness.email.sent)
    known = forgot(harness)
    unknown = forgot(harness, email="nobody@example.com")

    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json())
    assert len(harness.email.sent) == sent_before + 1  # only the real account got mail


# ── Rate limits and CSRF ─────────────────────────────────────────────────────


def test_login_is_rate_limited_per_email(harness):
    for _ in range(10):
        assert login(harness, password="wrong password here").status_code == 401
    r = login(harness, password="wrong password here")

    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    # Other accounts aren't affected.
    assert login(harness, email="someone@example.com").status_code == 401


def test_signup_is_rate_limited_per_ip(harness):
    for i in range(5):
        assert signup(harness, email=f"user{i}@example.com").status_code == 202
    assert signup(harness, email="user5@example.com").status_code == 429


def test_cross_site_requests_are_blocked(harness):
    signed_up_and_confirmed(harness)

    r = harness.client.post("/api/auth/logout", headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403
    r = harness.client.post("/api/c02/estimate", json={}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    assert harness.services.requests == []

    same_origin = {"sec-fetch-site": "same-origin", "origin": APP_URL}
    assert harness.client.post("/api/c02/estimate", json={}, headers=same_origin).status_code == 200
    assert harness.client.post("/api/c02/estimate", json={}, headers={"origin": APP_URL}).status_code == 200


# ── The proxy ────────────────────────────────────────────────────────────────


def test_services_are_only_reachable_when_signed_in(harness):
    r = harness.client.get("/api/c02/health")
    assert r.status_code == 401
    assert r.json() == {"detail": "Not signed in."}
    assert harness.services.requests == []

    signed_up_and_confirmed(harness)
    assert harness.client.get("/api/c02/health").status_code == 200
    assert "cookie" not in harness.services.requests[0].headers


# ── Housekeeping ─────────────────────────────────────────────────────────────


def test_cleanup_removes_only_dead_rows(harness):
    signed_up_and_confirmed(harness)  # one live session, one used token
    forgot(harness)  # one live token
    harness.sql(
        "INSERT INTO sessions (id_hash, user_id, remember_me, created_at, last_seen_at,"
        " idle_expires_at, absolute_expires_at)"
        " SELECT repeat('0', 64), id, false, now(), now(), now() - interval '1 second',"
        " now() + interval '1 hour' FROM users"
    )
    harness.sql("INSERT INTO rate_limits VALUES ('old', now() - interval '2 days', 1)")

    async def run():
        engine = create_async_engine(harness.database_url)
        async with async_sessionmaker(engine)() as db:
            await cleanup_expired(db)
            await db.commit()
        await engine.dispose()

    asyncio.run(run())

    assert harness.sql("SELECT id_hash = repeat('0', 64) FROM sessions") == [(False,)]
    assert harness.sql("SELECT purpose FROM email_tokens") == [("reset_password",)]
    assert harness.sql("SELECT count(*) FROM rate_limits WHERE key = 'old'") == [(0,)]


def test_migrations_match_the_models(database_url):
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()
    assert diff == []

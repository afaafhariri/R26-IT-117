"""Sign-up, email confirmation, login, logout and password reset.

None of these responses reveal whether an email address has an account.
Sign-up, "send a new link" and "forgot password" answer the same way either
way; the difference is only in what lands in that inbox, which only its
owner can read.
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.auth.guards import check_origin, client_ip, hit, too_many_attempts
from app.auth.passwords import (
    DUMMY_HASH,
    hash_password,
    needs_rehash,
    password_problem,
    verify_password,
)
from app.auth.sessions import (
    clear_session_cookie,
    cookie_name,
    create_session,
    require_user,
    revoke_all_sessions,
    revoke_session,
    set_session_cookie,
)
from app.auth.tokens import (
    RESET_PASSWORD,
    VERIFY_EMAIL,
    consume_email_token,
    issue_email_token,
    peek_email_token,
)
from app.config import Settings
from app.db import get_db, utcnow
from app.email import (
    Email,
    account_exists_message,
    deliver,
    password_changed_message,
    reset_password_message,
    verify_email_message,
)
from app.models import Account, User

router = APIRouter(prefix="/api/auth", tags=["Auth"], dependencies=[Depends(check_origin)])

FIFTEEN_MINUTES = timedelta(minutes=15)
HOUR = timedelta(hours=1)

# Caps the input to Argon2, which would otherwise happily hash megabytes.
_PASSWORD_FIELD = Field(max_length=1024)


class SignupIn(BaseModel):
    email: EmailStr
    password: str = _PASSWORD_FIELD


class LoginIn(SignupIn):
    remember_me: bool = False


class EmailIn(BaseModel):
    email: EmailStr


class VerifyIn(BaseModel):
    token: str = Field(max_length=128)
    password: str = _PASSWORD_FIELD
    remember_me: bool = False


class ResetIn(BaseModel):
    token: str = Field(max_length=128)
    password: str = _PASSWORD_FIELD


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    email_verified: bool

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(id=user.id, email=user.email, email_verified=user.email_verified_at is not None)


class Message(BaseModel):
    message: str


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _link(request: Request, path: str, token: str | None = None) -> str:
    # The token goes in the #fragment, which browsers never send to a server
    # or put in a Referer header, so it can't leak from the page it opens.
    url = f"{_settings(request).app_base_url}{path}"
    return f"{url}#token={token}" if token else url


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _send(request: Request, background: BackgroundTasks, email: Email) -> None:
    background.add_task(deliver, request.app.state.email, email)


async def _limit(db: AsyncSession, *rules: tuple[str, int, timedelta]) -> None:
    for key, limit, window in rules:
        retry_after = await hit(db, key, limit, window)
        if retry_after is not None:
            await db.commit()
            raise too_many_attempts(retry_after)
    await db.commit()


async def _start_session(
    db: AsyncSession, request: Request, response: Response, user: User, remember_me: bool
) -> None:
    # A session cookie that arrives with a login is ended, never carried over,
    # so nobody can plant a session ID in a browser before the user logs in.
    settings = _settings(request)
    if old := request.cookies.get(cookie_name(settings)):
        await revoke_session(db, old)
    raw = await create_session(db, user.id, remember_me, request)
    user.last_login_at = utcnow()
    set_session_cookie(response, settings, raw, remember_me)


@router.post("/signup", status_code=status.HTTP_202_ACCEPTED, response_model=Message)
async def signup(
    body: SignupIn,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    await _limit(db, (f"signup:ip:{client_ip(request)}", 5, HOUR))
    if problem := password_problem(body.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)

    email = _normalise_email(body.email)
    # Hashed before the lookup, so a new and an existing address take equally long.
    password_hash = await run_in_threadpool(hash_password, body.password)

    existing = await db.scalar(select(User).where(User.email == email))
    if existing is None:
        account = Account()
        db.add(account)
        await db.flush()
        user = User(account_id=account.id, email=email, password_hash=password_hash)
        db.add(user)
        try:
            await db.flush()
        except IntegrityError:
            # The same address signed up a moment ago; treat it as existing.
            await db.rollback()
            existing = await db.scalar(select(User).where(User.email == email))
        else:
            raw = await issue_email_token(db, user.id, VERIFY_EMAIL)
            await db.commit()
            _send(request, background, verify_email_message(email, _link(request, "/verify-email", raw)))

    if existing is not None:
        # The password just entered is discarded. For an unconfirmed account
        # that matters: whoever signed up first chose its password, and only
        # the inbox owner can replace it (via reset), so a stranger who
        # registered someone else's address first can never get in.
        _send(
            request,
            background,
            account_exists_message(
                email, _link(request, "/login"), _link(request, "/forgot-password")
            ),
        )

    return Message(message="Check your email for a link to finish signing up.")


@router.post("/verify-email", response_model=UserOut)
async def verify_email(
    body: VerifyIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Confirms the address and signs in. Needs the emailed link *and* the
    account's password, so a link opened by anyone else (or fetched by an
    email scanner) can't activate the account."""
    await _limit(db, (f"login:ip:{client_ip(request)}", 30, FIFTEEN_MINUTES))

    token = await peek_email_token(db, body.token, VERIFY_EMAIL)
    if token is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This link is invalid or has expired. Log in to get a new one.",
        )
    user = await db.get(User, token.user_id)
    if not await run_in_threadpool(verify_password, user.password_hash, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect password.")
    if await consume_email_token(db, body.token, VERIFY_EMAIL) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This link has already been used.")

    user.email_verified_at = utcnow()
    await _start_session(db, request, response, user, body.remember_me)
    await db.commit()
    return UserOut.of(user)


@router.post("/verify-email/resend", status_code=status.HTTP_202_ACCEPTED, response_model=Message)
async def resend_verification(
    body: EmailIn,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    email = _normalise_email(body.email)
    await _limit(
        db,
        (f"resend:ip:{client_ip(request)}", 10, HOUR),
        (f"resend:email:{email}", 3, HOUR),
    )
    user = await db.scalar(select(User).where(User.email == email))
    if user is not None and user.email_verified_at is None:
        raw = await issue_email_token(db, user.id, VERIFY_EMAIL)
        await db.commit()
        _send(request, background, verify_email_message(email, _link(request, "/verify-email", raw)))
    return Message(message="If that address has an unconfirmed account, we've sent a new link.")


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email = _normalise_email(body.email)
    await _limit(
        db,
        (f"login:ip:{client_ip(request)}", 30, FIFTEEN_MINUTES),
        (f"login:email:{email}", 10, FIFTEEN_MINUTES),
    )

    user = await db.scalar(select(User).where(User.email == email))
    password_ok = await run_in_threadpool(
        verify_password, user.password_hash if user else DUMMY_HASH, body.password
    )
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if user.email_verified_at is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Confirm your email before logging in. Check your inbox, or send a new link.",
        )

    if needs_rehash(user.password_hash):
        user.password_hash = await run_in_threadpool(hash_password, body.password)
    await _start_session(db, request, response, user, body.remember_me)
    await db.commit()
    return UserOut.of(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    settings = _settings(request)
    if raw := request.cookies.get(cookie_name(settings)):
        await revoke_session(db, raw)
        await db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, settings)
    return response


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(require_user)):
    return UserOut.of(user)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED, response_model=Message)
async def forgot_password(
    body: EmailIn,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    email = _normalise_email(body.email)
    await _limit(
        db,
        (f"forgot:ip:{client_ip(request)}", 10, HOUR),
        (f"forgot:email:{email}", 3, HOUR),
    )
    user = await db.scalar(select(User).where(User.email == email))
    if user is not None:
        raw = await issue_email_token(db, user.id, RESET_PASSWORD)
        await db.commit()
        _send(request, background, reset_password_message(email, _link(request, "/reset-password", raw)))
    return Message(message="If that address has an account, we've sent a link to reset the password.")


@router.post("/password/reset", response_model=Message)
async def reset_password(
    body: ResetIn,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    await _limit(db, (f"reset:ip:{client_ip(request)}", 20, HOUR))
    # Checked before the token is used up, so a rejected password doesn't
    # cost the user their link.
    if problem := password_problem(body.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)

    user_id = await consume_email_token(db, body.token, RESET_PASSWORD)
    if user_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This link is invalid or has expired. Ask for a new one.",
        )
    user = await db.get(User, user_id)
    user.password_hash = await run_in_threadpool(hash_password, body.password)
    if user.email_verified_at is None:
        # Opening the link proves they own the inbox.
        user.email_verified_at = utcnow()
    await revoke_all_sessions(db, user.id)
    await db.commit()
    # This browser's session was among those just ended; drop its cookie too.
    clear_session_cookie(response, _settings(request))

    _send(request, background, password_changed_message(user.email, _link(request, "/forgot-password")))
    return Message(message="Password changed. Log in with your new password.")

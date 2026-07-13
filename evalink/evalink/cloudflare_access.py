"""
Cloudflare Access (Zero Trust) SSO integration.

When a request passes through a Cloudflare Access application, Cloudflare adds
Cf-Access-Jwt-Assertion with a signed JWT. We validate that token and log the
user into a Django session, creating a non-admin account on first visit.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from urllib.parse import urlparse

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)

JWT_HEADER = 'HTTP_CF_ACCESS_JWT_ASSERTION'
CERT_CACHE_SECONDS = 3600
_TEAM_DOMAIN_RE = re.compile(r'^[a-z0-9-]+\.cloudflareaccess\.com$', re.IGNORECASE)

_cert_cache_lock = threading.Lock()
_cert_cache: dict[str, tuple[float, jwt.PyJWKClient]] = {}


def _enabled() -> bool:
    return bool(getattr(settings, 'CLOUDFLARE_ACCESS_ENABLED', False))


def normalize_team_domain(raw: str) -> str:
    """Return host like myteam.cloudflareaccess.com from env/dashboard values."""
    value = (raw or '').strip().rstrip('/')
    if not value:
        return ''
    if '://' in value:
        value = urlparse(value).netloc or value
    if not value.endswith('.cloudflareaccess.com'):
        value = f'{value}.cloudflareaccess.com'
    if not _TEAM_DOMAIN_RE.match(value):
        raise ValueError(f'Invalid Cloudflare Access team domain: {raw!r}')
    return value.lower()


def team_issuer(team_domain: str) -> str:
    return f'https://{team_domain}'


def certs_url(team_domain: str) -> str:
    return f'{team_issuer(team_domain)}/cdn-cgi/access/certs'


def _get_jwks_client(team_domain: str) -> jwt.PyJWKClient:
    now = time.time()
    with _cert_cache_lock:
        cached = _cert_cache.get(team_domain)
        if cached and cached[0] > now:
            return cached[1]
        client = jwt.PyJWKClient(certs_url(team_domain), cache_keys=True)
        _cert_cache[team_domain] = (now + CERT_CACHE_SECONDS, client)
        return client


def clear_cert_cache() -> None:
    """Testing helper: drop cached JWKS clients."""
    with _cert_cache_lock:
        _cert_cache.clear()


def decode_access_token(token: str) -> dict:
    """
    Validate Cf-Access-Jwt-Assertion and return JWT claims.

    Raises jwt.PyJWTError on invalid or untrusted tokens.
    """
    team_domain = normalize_team_domain(settings.CLOUDFLARE_ACCESS_TEAM_DOMAIN)
    audience = (settings.CLOUDFLARE_ACCESS_AUD or '').strip()
    if not team_domain or not audience:
        raise jwt.InvalidTokenError('Cloudflare Access is not configured')

    signing_key = _get_jwks_client(team_domain).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=['RS256'],
        audience=audience,
        issuer=team_issuer(team_domain),
        options={'require': ['exp', 'email']},
    )


def username_for_email(email: str) -> str:
    """Derive a unique Django username from an email address."""
    email = email.strip().lower()
    base = email.replace('@', '_at_')
    if len(base) <= 150:
        candidate = base
    else:
        local, _, domain = email.partition('@')
        candidate = f'{local}_at_{domain}'[:150]

    User = get_user_model()
    if not User.objects.filter(username=candidate).exists():
        return candidate

    suffix = 2
    while True:
        tail = f'_{suffix}'
        truncated = candidate[: 150 - len(tail)] + tail
        if not User.objects.filter(username=truncated).exists():
            return truncated
        suffix += 1


def get_or_create_user_from_claims(claims: dict) -> AbstractBaseUser:
    """Find or create a non-admin Django user from Access JWT claims."""
    email = (claims.get('email') or '').strip()
    if not email:
        raise ValueError('Cloudflare Access token is missing email')

    User = get_user_model()
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        user = User.objects.create(
            username=username_for_email(email),
            email=email,
            is_staff=False,
            is_superuser=False,
        )
        user.set_unusable_password()
        user.save()
        logger.info('Created Django user for Cloudflare Access identity %s', email)
    elif not user.has_usable_password():
        # Keep email in sync if an admin corrected the account later.
        normalized = email.lower()
        if user.email.lower() != normalized:
            user.email = email
            user.save(update_fields=['email'])

    return user


def authenticate_request(request) -> AbstractBaseUser | None:
    """
    If the request carries a valid Access JWT, return the Django user.
    Returns None when Access is disabled, the header is absent, or the user
    already has a matching authenticated session.
    """
    if not _enabled():
        return None

    token = request.META.get(JWT_HEADER, '').strip()
    if not token:
        return None

    if request.user.is_authenticated:
        session_email = (request.user.email or '').strip().lower()
        try:
            claims = decode_access_token(token)
        except jwt.PyJWTError:
            logger.warning('Ignoring invalid Cloudflare Access token for authenticated session')
            return None
        token_email = (claims.get('email') or '').strip().lower()
        if session_email and token_email and session_email == token_email:
            return None
        # Access identity changed (or session user has no email); re-bind session.
        user = get_or_create_user_from_claims(claims)
        if user.pk != request.user.pk:
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return user

    try:
        claims = decode_access_token(token)
    except jwt.PyJWTError as exc:
        logger.warning('Rejected Cloudflare Access token: %s', exc)
        return None

    user = get_or_create_user_from_claims(claims)
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return user

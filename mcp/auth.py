# -*- coding: utf-8 -*-
"""
JWT bearer-token verification for Sewa Setu MCP servers.

The portal is an OAuth 2.1 AS issuing RS256 JWTs. Every MCP tool call
must carry a valid Bearer token in the Authorization header.

We cache the JWKS for 1 hour to avoid hammering the portal on every call.
"""
import time
import os
import jwt
from jwt import PyJWKClient, PyJWKClientError
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

PORTAL_URL = os.environ.get("PORTAL_URL", "http://app:8000")
JWKS_URL   = PORTAL_URL + "/.well-known/jwks.json"
ISSUER     = os.environ.get("PORTAL_ISSUER",
               os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")).rstrip("/")

# ── JWKS client with 1-hour cache ──────────────────────────────────────────
_jwks_client: PyJWKClient | None = None
_jwks_fetched_at: float = 0.0
JWKS_TTL = 3600


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client, _jwks_fetched_at
    if _jwks_client is None or (time.time() - _jwks_fetched_at) > JWKS_TTL:
        _jwks_client = PyJWKClient(JWKS_URL, cache_keys=True)
        _jwks_fetched_at = time.time()
    return _jwks_client


_security = HTTPBearer(auto_error=False)


def _decode(token: str, audience: str) -> dict:
    client = _get_jwks_client()
    try:
        signing_key = client.get_signing_key_from_jwt(token)
    except PyJWKClientError as e:
        raise HTTPException(status_code=401, detail=f"JWKS error: {e}")
    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=ISSUER,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401,
                            detail="Token has expired. Please sign in again.")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=401,
                            detail="Token audience does not match this server.")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    return claims


def require_citizen(audience: str):
    """Returns a FastAPI dependency that validates a citizen-scope token."""
    def _dep(creds: HTTPAuthorizationCredentials = Security(_security)):
        if not creds:
            raise HTTPException(status_code=401,
                                detail="Authorization header required.")
        claims = _decode(creds.credentials, audience)
        if claims.get("scope") != "citizen":
            raise HTTPException(status_code=403,
                                detail="citizen scope required.")
        return claims
    return _dep


def require_officer(audience: str):
    """Returns a FastAPI dependency that validates an officer-scope token."""
    def _dep(creds: HTTPAuthorizationCredentials = Security(_security)):
        if not creds:
            raise HTTPException(status_code=401,
                                detail="Authorization header required.")
        claims = _decode(creds.credentials, audience)
        if claims.get("scope") != "officer":
            raise HTTPException(status_code=403,
                                detail="officer scope required.")
        return claims
    return _dep

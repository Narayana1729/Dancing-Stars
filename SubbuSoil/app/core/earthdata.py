"""NASA Earthdata Login helpers.

Credentials come from backend/.env via Settings. A token is preferred when both
a token and username/password are present.
"""
from functools import lru_cache

import asf_search as asf

from app.core.config import get_settings


class EarthdataNotConfigured(RuntimeError):
    pass


@lru_cache
def get_asf_session() -> asf.ASFSession:
    """Authenticated ASF session, used for search, download and streaming."""
    s = get_settings()
    session = asf.ASFSession()
    if s.earthdata_token:
        return session.auth_with_token(s.earthdata_token.get_secret_value())
    if s.earthdata_username and s.earthdata_password:
        return session.auth_with_creds(
            s.earthdata_username, s.earthdata_password.get_secret_value()
        )
    raise EarthdataNotConfigured(
        "Set EARTHDATA_TOKEN or EARTHDATA_USERNAME/EARTHDATA_PASSWORD in backend/.env"
    )

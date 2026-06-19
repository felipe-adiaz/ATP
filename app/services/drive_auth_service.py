import os
from google_auth_oauthlib.flow import Flow

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _build_flow() -> Flow:
    client_config = {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.environ["GOOGLE_REDIRECT_URI"]],
        }
    }
    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, autogenerate_code_verifier=False
    )
    flow.redirect_uri = os.environ["GOOGLE_REDIRECT_URI"]
    return flow


def gerar_url_autorizacao(state: str) -> str:
    flow = _build_flow()
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return url


def trocar_code_por_tokens(code: str) -> dict:
    flow = _build_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }

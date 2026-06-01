import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from config import CLIENT_SECRET_FILE, TOKEN_FILE, YOUTUBE_SCOPES


logger = logging.getLogger(__name__)


def get_credentials(
    client_secret_file: Path = CLIENT_SECRET_FILE,
    token_file: Path = TOKEN_FILE,
) -> Credentials:
    """Load, refresh, or create YouTube OAuth credentials."""
    credentials = None

    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(str(token_file), YOUTUBE_SCOPES)

    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        logger.info("Refreshing expired YouTube access token.")
        credentials.refresh(Request())
    else:
        if not client_secret_file.exists():
            raise FileNotFoundError(
                f"Missing OAuth client file: {client_secret_file}. "
                "Download it from Google Cloud Console and save it as client_secret.json."
            )

        logger.info("Starting YouTube OAuth browser login.")
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), YOUTUBE_SCOPES)
        credentials = flow.run_local_server(port=0, prompt="consent")

    token_file.write_text(credentials.to_json(), encoding="utf-8")
    logger.info("Saved YouTube OAuth token to %s", token_file)
    return credentials

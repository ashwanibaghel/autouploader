import logging
import os
from pathlib import Path

import requests

from config import (
    DEFAULT_INSTAGRAM_GRAPH_BASE_URL,
    DEFAULT_INSTAGRAM_GRAPH_API_VERSION,
    INSTAGRAM_ACCESS_TOKEN_ENV,
    INSTAGRAM_GRAPH_BASE_URL_ENV,
    INSTAGRAM_GRAPH_API_VERSION_ENV,
    PROJECT_ROOT,
)
from instagram_publisher import load_dotenv_if_present, parse_graph_response


logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    load_dotenv_if_present()
    token = require_env(INSTAGRAM_ACCESS_TOKEN_ENV)
    graph_version = os.environ.get(
        INSTAGRAM_GRAPH_API_VERSION_ENV,
        DEFAULT_INSTAGRAM_GRAPH_API_VERSION,
    )
    graph_base_url = os.environ.get(
        INSTAGRAM_GRAPH_BASE_URL_ENV,
        DEFAULT_INSTAGRAM_GRAPH_BASE_URL,
    ).rstrip("/")

    response = requests.get(
        f"{graph_base_url}/me",
        params={
            "fields": "id,username,account_type,media_count",
            "access_token": token,
        },
        timeout=30,
    )
    if response.ok:
        profile = parse_graph_response(response)
        logging.info("INSTAGRAM_USER_ID=%s", profile.get("id"))
        logging.info("Instagram username=%s", profile.get("username") or "")
        logging.info("Account type=%s", profile.get("account_type") or "")
        return

    response = requests.get(
        f"https://graph.facebook.com/{graph_version}/me/accounts",
        params={
            "fields": "name,id,instagram_business_account{id,username,name}",
            "access_token": token,
        },
        timeout=30,
    )
    payload = parse_graph_response(response)
    accounts = payload.get("data", [])

    found = False
    for page in accounts:
        instagram = page.get("instagram_business_account")
        if not instagram:
            continue
        found = True
        logging.info("Page: %s (%s)", page.get("name"), page.get("id"))
        logging.info("INSTAGRAM_USER_ID=%s", instagram.get("id"))
        logging.info("Instagram username=%s", instagram.get("username") or "")
        logging.info("")

    if not found:
        logging.info(
            "No connected Instagram Business account found. Make sure the Instagram account "
            "is professional and connected to a Facebook Page, and the token has the required permissions."
        )


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing {name}. Add it to .env.")
    return value


if __name__ == "__main__":
    main()

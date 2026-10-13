"""Single-alias Addy.io to Gmail delivery test (metadata only).

Usage:
  python scripts/addy_gmail_test.py token
  python scripts/addy_gmail_test.py create
  python scripts/addy_gmail_test.py check --alias ALIAS@anonaddy.me

This diagnostic is independent of the Instagram signup flow.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import time
from email.utils import getaddresses
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".private"
ADDY_API_BASE = "https://app.addy.io/api/v1"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.metadata"
MAIL_HEADERS = [
    "To", "Cc", "Delivered-To", "X-Original-To", "X-Forwarded-To", "Apparently-To"
]


def addy_request(method: str, route: str, *, data: dict | None = None) -> dict:
    """Authenticate without writing keys to disk or command-line history."""
    key = os.environ.get("ADDY_API_TOKEN", "").strip()
    if not key:
        key = getpass.getpass("Addy.io API token (hidden): ").strip()
    if not key:
        raise RuntimeError("Missing Addy API token")
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    request = Request(
        ADDY_API_BASE + route,
        data=payload,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    try:
        with urlopen(request, timeout=25) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"Addy.io returned HTTP {exc.code}") from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Addy.io network request failed") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Unexpected Addy.io API response")
    return result


def create_alias(
    domain: str, recipient_id: str | None = None, name: str | None = None
) -> tuple[str, str]:
    """Create one alias; optionally use a readable custom local part."""
    if name is not None:
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,62}", name):
            raise ValueError("Invalid alias name: use 2-63 Latin letters, digits, dots, underscores or hyphens")
    body: dict = {
        "domain": domain,
        "format": "custom" if name else "uuid",
        "description": "Personal Addy to Gmail delivery test",
    }
    if name:
        body["local_part"] = name
    if recipient_id:
        body["recipient_ids"] = [recipient_id]
    result = addy_request("POST", "/aliases", data=body).get("data") or {}
    alias_id, address = result.get("id"), result.get("email")
    if not alias_id or not address:
        raise RuntimeError("Addy.io response did not contain alias id and email")
    return str(alias_id), str(address)


def gmail_client():
    """Use read-only Gmail metadata OAuth and cache the local refresh token."""
    try:
        from google.auth.transport.requests import Request as AuthRequest
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Install dependencies: python -m pip install -r requirements-addy-gmail.txt"
        ) from exc

    credentials_file = PRIVATE / "credentials.json"
    token_file = PRIVATE / "gmail_token.json"
    if not credentials_file.is_file():
        raise RuntimeError(
            f"Missing {credentials_file}. Download a Desktop OAuth client JSON from Google Cloud."
        )
    credentials = None
    if token_file.is_file():
        credentials = Credentials.from_authorized_user_file(str(token_file), [GMAIL_SCOPE])
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(AuthRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), [GMAIL_SCOPE])
            credentials = flow.run_local_server(port=0)
        PRIVATE.mkdir(parents=True, exist_ok=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")
        try:
            os.chmod(token_file, 0o600)
        except OSError:
            pass
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def extract_header_emails(headers: list[dict]) -> set[str]:
    """Read only recipient headers; never fetch the mail body."""
    accepted = {h.lower() for h in MAIL_HEADERS}
    values = [
        str(item.get("value", ""))
        for item in headers
        if str(item.get("name", "")).lower() in accepted
    ]
    return {address.strip().lower() for _, address in getaddresses(values) if address}


def matches_alias(headers: list[dict], alias: str) -> bool:
    return alias.strip().lower() in extract_header_emails(headers)


def check_gmail_alias(service, alias: str, minutes: int, max_messages: int) -> bool:
    """Scan recent headers: Gmail's gmail.metadata scope forbids the q filter."""
    cutoff = int((time.time() - minutes * 60) * 1000)
    remaining = max_messages
    page_token = None
    while remaining > 0:
        options: dict = {
            "userId": "me",
            "maxResults": min(100, remaining),
            "includeSpamTrash": True,
        }
        if page_token:
            options["pageToken"] = page_token
        page = service.users().messages().list(**options).execute()
        messages = page.get("messages", [])
        for item in messages:
            message = service.users().messages().get(
                userId="me", id=item["id"], format="metadata", metadataHeaders=MAIL_HEADERS
            ).execute()
            received = int(message.get("internalDate", "0"))
            if received >= cutoff and matches_alias(message.get("payload", {}).get("headers", []), alias):
                print(f"[OK] Gmail received mail addressed to {alias}.")
                print("Only message metadata (headers) was read.")
                return True
        remaining -= len(messages)
        page_token = page.get("nextPageToken")
        if not page_token or not messages:
            break
    print("[NOT FOUND] No matching recent Gmail metadata.")
    print("Check Addy forwarding/recipient, Gmail Spam, time window and forwarding headers.")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Single-alias Addy.io to Gmail delivery test")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("token", help="Check Addy API token (read-only)")
    create = sub.add_parser("create", help="Create ONE Addy alias")
    create.add_argument("--domain", default="anonaddy.me")
    create.add_argument("--name", help="Custom readable alias local part (Addy.io plan restrictions may apply)")
    create.add_argument("--recipient-id", help="Optional verified Addy recipient ID")
    check = sub.add_parser("check", help="Find forwarded mail using Gmail headers only")
    check.add_argument("--alias", required=True)
    check.add_argument("--minutes", type=int, default=60)
    check.add_argument("--max-messages", type=int, default=100)
    args = parser.parse_args(argv)
    try:
        if args.command == "token":
            result = addy_request("GET", "/api-token-details")
            if not result.get("data"):
                raise RuntimeError("API token details not returned")
            print("[OK] Addy.io API token accepted")
            return 0
        if args.command == "create":
            _, address = create_alias(args.domain, args.recipient_id, args.name)
            print("[OK] One alias created:")
            print(address)
            print("Send a test email from another address to this alias.")
            return 0
        if "@" not in args.alias or args.minutes < 1 or not 1 <= args.max_messages <= 500:
            parser.error("Expected --alias EMAIL, --minutes >= 1, --max-messages 1..500")
        found = check_gmail_alias(gmail_client(), args.alias, args.minutes, args.max_messages)
        return 0 if found else 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

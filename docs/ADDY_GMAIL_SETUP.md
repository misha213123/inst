# Addy.io → Gmail: delivery check (PowerShell)

This is a **single-alias, metadata-only test**, independent of the Instagram signup workflow. It does not read message bodies or extract confirmation codes.

## Install

Open PowerShell in the checked-out repository (example):

    cd "C:\Users\blackpansel\Desktop\Instagram-Bloks-Signup"
    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements-addy-gmail.txt

If the virtual environment already exists, skip the venv creation.

## Addy.io forwarding

1. Check at https://app.addy.io/recipients that your Gmail recipient is verified, and either make it the default or note its recipient ID.
2. Create a personal Addy.io API token at https://app.addy.io/settings/api and **do not put it in GitHub**.
3. Run:

    .\.venv\Scripts\python.exe scripts\addy_gmail_test.py token
    .\.venv\Scripts\python.exe scripts\addy_gmail_test.py create

For a readable alias name instead of a UUID, run:

    .\\.venv\\Scripts\\python.exe scripts\\addy_gmail_test.py create --name privet-test

This submits `format=custom` and `local_part=privet-test` to Addy.io. The exact resulting address can include an automatically appended suffix; always use the email printed by the API. Custom names on shared domains may require a paid plan.

The tool prompts for the API key without echoing. The default domain is `anonaddy.me` and the alias format is UUID when `--name` is omitted. If your plan uses another allowed domain, specify `create --domain YOUR-DOMAIN`. To route directly to a verified recipient, specify `--recipient-id RECIPIENT-ID`.

`create` creates exactly **one** alias and prints the address. Send a harmless test email to that alias from a different mailbox.

## Gmail OAuth

1. In https://console.cloud.google.com/ create/select a project, enable Gmail API.
2. Configure the OAuth consent screen (your Gmail as a test user when applicable).
3. Create an OAuth client of type **Desktop app**.
4. Download the client JSON file as `.private/credentials.json` inside this repository.
5. Run with the address returned above:

    .\.venv\Scripts\python.exe scripts\addy_gmail_test.py check --alias "YOUR-ALIAS@anonaddy.me"

The first run opens a browser for Google sign-in. OAuth uses the minimum `gmail.metadata` scope: the tool reads recipients from message headers, not bodies, and stores its refresh token locally at `.private/gmail_token.json`.

For a wider time/search window:

    .\.venv\Scripts\python.exe scripts\addy_gmail_test.py check --alias "YOUR-ALIAS@anonaddy.me" --minutes 180 --max-messages 200

Note: Gmail API does **not** support the `q` query parameter with `gmail.metadata`. This script inspects recent message metadata (including Spam and Trash), so a false negative can occur if a message is outside the scanned window or the original alias was not preserved in forwarding headers.

## Security and testing

Never publish `.private/`, `.env`, API keys, Google OAuth JSON or `hits.csv`. Run offline unit tests:

    py -3 -m unittest discover -s tests -p "test_addy_gmail_test.py" -v

References: https://app.addy.io/docs/ and https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list

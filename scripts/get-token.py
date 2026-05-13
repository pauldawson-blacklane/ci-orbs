#!/usr/bin/env python3
"""Mint a GitHub App installation access token and persist it for downstream CI steps.

Designed to be the FIRST step of a multi-step CircleCI job that needs to call the
GitHub API. After this script runs, subsequent steps in the SAME job can use
`$GH_TOKEN` directly (bash auto-sources `$BASH_ENV` before each step).

How the credential chain works:

    Private key (PEM)   ──signs──▶   JWT (10-min max)   ──exchanged at──▶   Installation token (1 hour)
    ↑ stored as a                    ↑ disposable,                          ↑ what we actually USE
      CircleCI env var                 in-memory only                         to call the GH API

The PEM is the durable secret (rotate manually, on a schedule).
The JWT proves we hold the PEM.
The installation token is the short-lived bearer credential issued by GitHub.

Required env vars (set as CircleCI project env vars):
    GH_APP_ID                 numeric App ID, used as JWT `iss` claim
    GH_APP_INSTALLATION_ID    numeric ID identifying which install to mint the token against
    GH_APP_PRIVATE_KEY_B64    base64-encoded PEM private key (single-line, fits env var)
"""
import base64
import json
import os
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import jwt  # PyJWT — handles RS256 signing


def format_expiry(iso_utc: str) -> list[str]:
    """Render the token expiry across UTC, UK and Germany time zones for the demo audience.

    GitHub always returns expiry as ISO 8601 in UTC (trailing 'Z'). The audience for
    this demo spans UK and DE offices, so we present all three zones for clarity.
    Zone abbreviations (BST/GMT, CEST/CET) adjust automatically for daylight saving.
    """
    # Python's fromisoformat() doesn't accept the 'Z' shorthand until 3.11, so
    # normalise it to '+00:00' for portability.
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    zones = [
        ("UTC",     ZoneInfo("UTC")),
        ("UK",      ZoneInfo("Europe/London")),
        ("Germany", ZoneInfo("Europe/Berlin")),
    ]
    lines = []
    for label, tz in zones:
        local = dt.astimezone(tz)
        lines.append(f"    {label:<8} {local.strftime('%Y-%m-%d %H:%M:%S %Z (%z)')}")
    return lines


def main():
    # ---- Step 0: collect inputs from environment --------------------------------
    app_id = os.environ["GH_APP_ID"]
    install_id = os.environ["GH_APP_INSTALLATION_ID"]
    pem_b64 = os.environ["GH_APP_PRIVATE_KEY_B64"]

    # CircleCI env-var UI sometimes strips trailing '=' chars (base64 padding).
    # Add the right number of '=' back before decoding so the PEM parses cleanly.
    private_key = base64.b64decode(pem_b64 + "=" * (-len(pem_b64) % 4)).decode()

    # ---- Step 1: build and sign the JWT ----------------------------------------
    # GitHub enforces: exp must be <= iat + 600 seconds (10 minutes).
    # We backdate iat by 60s to tolerate clock skew between this runner and GitHub
    # (otherwise 'iat in the future' rejections can occur on busy CI runners), and
    # set exp to now+540s — well inside the 10-min ceiling.
    now = int(time.time())
    payload = {
        "iat": now - 60,    # issued-at, with 60s skew buffer
        "exp": now + 540,   # expires-at, 9 minutes from now
        "iss": app_id,      # issuer — tells GitHub which App's public key to verify against
    }
    # RS256 = RSA signature with SHA-256. The App was created with an RSA keypair;
    # GitHub keeps the public half, we hold the private half (the PEM above).
    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")

    # ---- Step 2: exchange the JWT for an installation access token -------------
    # GitHub returns the actual usable token (`ghs_…`) with a fixed 1-hour TTL.
    # The endpoint is documented under "Create an installation access token for an app".
    # Note: POST with no body is intentional — all params are in the URL/headers.
    req = urllib.request.Request(
        f"https://api.github.com/app/installations/{install_id}/access_tokens",
        method="POST",
        data=b"",  # empty body; GitHub still expects POST
    )
    req.add_header("Authorization", f"Bearer {encoded_jwt}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())

    token = body["token"]              # ghs_… 40-char installation token
    expires = body["expires_at"]       # ISO 8601 UTC, exactly 1h from issuance

    # ---- Step 3: print human-readable demo output ------------------------------
    # Useful for the CI log so anyone debugging can see exactly what was minted.
    # In production you might suppress the raw token; we display it here for the
    # demo so the audience can see the actual credential being issued.
    width = 78
    print("=" * width)
    print(" GitHub App installation token issued")
    print("=" * width)
    print(f"  token:                {token}")
    print(f"  expires_at (raw):     {expires}")
    print(f"  expires_at by zone:")
    for line in format_expiry(expires):
        print(line)
    print(f"  repository_selection: {body['repository_selection']}")
    print(f"  permissions:")
    for k, v in sorted(body["permissions"].items()):
        print(f"    - {k}: {v}")
    print()

    # ---- Step 4: persist the token for downstream CircleCI steps ---------------
    # CircleCI sources $BASH_ENV before each step in the same job, so appending
    # `export GH_TOKEN=…` here makes it available in steps 2, 3, 4 etc. of the
    # same job. The variable lives only for the duration of this job.
    bash_env = os.environ.get("BASH_ENV")
    if bash_env:
        with open(bash_env, "a") as f:
            f.write(f"export GH_TOKEN={token}\n")
            f.write(f"export GH_TOKEN_EXPIRES={expires}\n")
        print(f"  exported GH_TOKEN and GH_TOKEN_EXPIRES to $BASH_ENV ({bash_env})")
    else:
        # If not running under CircleCI (e.g. local debug), there's no BASH_ENV.
        # Print a warning so the caller knows the token is only in stdout above.
        print("  WARNING: $BASH_ENV unset — token not persisted to downstream steps")


if __name__ == "__main__":
    main()

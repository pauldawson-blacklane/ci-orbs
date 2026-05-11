#!/usr/bin/env python3
"""Sign a JWT, exchange it for a GitHub App installation token, persist token to $BASH_ENV.

Designed to be one step of a multi-step CircleCI job.
Subsequent steps in the same job can use `$GH_TOKEN` directly (sourced from $BASH_ENV by bash).
"""
import base64
import json
import os
import time
import urllib.request

import jwt  # PyJWT


def main():
    app_id = os.environ["GH_APP_ID"]
    install_id = os.environ["GH_APP_INSTALLATION_ID"]
    pem_b64 = os.environ["GH_APP_PRIVATE_KEY_B64"]
    # tolerate stripped padding
    private_key = base64.b64decode(pem_b64 + "=" * (-len(pem_b64) % 4)).decode()

    # Sign JWT
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 540, "iss": app_id}
    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")

    # Exchange for installation token
    req = urllib.request.Request(
        f"https://api.github.com/app/installations/{install_id}/access_tokens",
        method="POST",
        data=b"",
    )
    req.add_header("Authorization", f"Bearer {encoded_jwt}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())

    token = body["token"]
    expires = body["expires_at"]

    # Visible-for-demo output
    width = 78
    print("=" * width)
    print(" GitHub App installation token issued")
    print("=" * width)
    print(f"  token:                {token}")
    print(f"  expires_at:           {expires}")
    print(f"  repository_selection: {body['repository_selection']}")
    print(f"  permissions:")
    for k, v in sorted(body["permissions"].items()):
        print(f"    - {k}: {v}")
    print()

    # Persist for downstream steps in the same CircleCI job
    bash_env = os.environ.get("BASH_ENV")
    if bash_env:
        with open(bash_env, "a") as f:
            f.write(f"export GH_TOKEN={token}\n")
            f.write(f"export GH_TOKEN_EXPIRES={expires}\n")
        print(f"  exported GH_TOKEN and GH_TOKEN_EXPIRES to $BASH_ENV ({bash_env})")
    else:
        print("  WARNING: $BASH_ENV unset — token not persisted to downstream steps")


if __name__ == "__main__":
    main()

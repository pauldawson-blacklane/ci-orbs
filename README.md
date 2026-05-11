# ci-orbs

Reusable CI helper scripts for CircleCI pipelines that integrate with a GitHub App.

## scripts/get-token.py

Generates a GitHub App installation access token and exports it to subsequent
CircleCI steps as `$GH_TOKEN` (via `$BASH_ENV`).

### Required env vars (set as CircleCI project env vars)

| Name | Purpose |
|---|---|
| `GH_APP_ID` | App ID (numeric) used as JWT `iss` |
| `GH_APP_INSTALLATION_ID` | Installation ID to mint the token against |
| `GH_APP_PRIVATE_KEY_B64` | base64-encoded PEM private key |

### Usage from another repo's `.circleci/config.yml`

```yaml
jobs:
  build:
    docker:
      - image: cimg/python:3.12
    steps:
      - checkout
      - run:
          name: Generate GitHub App installation token (via ci-orbs)
          command: |
            pip install --quiet PyJWT cryptography
            curl -sSfL https://raw.githubusercontent.com/pauldawson-blacklane/ci-orbs/main/scripts/get-token.py | python3 -
      - run:
          name: Use the token
          command: |
            curl -s -H "Authorization: token $GH_TOKEN" \
              https://api.github.com/repos/$CIRCLE_PROJECT_USERNAME/$CIRCLE_PROJECT_REPONAME
```

After the first step, `$GH_TOKEN` and `$GH_TOKEN_EXPIRES` are available to every
later step in the same job (CircleCI sources `$BASH_ENV` between steps).

## Versioning

Currently consumers pin to `main`. For production, pin to a git tag or commit
SHA so the script can't change underneath you without an explicit upgrade.

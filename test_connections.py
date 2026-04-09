"""Quick connection test for Jira and Bitbucket credentials.

Reads credentials from .env.example (or .env if present).
Run from the FORGE root:  python test_connections.py
"""
import sys
import os
import httpx
from dotenv import dotenv_values

sys.stdout.reconfigure(encoding="utf-8")

# Load from .env if it exists, otherwise fall back to .env.example
env_file = ".env" if os.path.exists(".env") else ".env.example"
cfg = dotenv_values(env_file)
print(f"Loading credentials from: {env_file}\n")

JIRA_URL      = cfg.get("JIRA_URL", "")
JIRA_USERNAME = cfg.get("JIRA_USERNAME", "")
JIRA_TOKEN    = cfg.get("JIRA_API_TOKEN", "")

BITBUCKET_USERNAME     = cfg.get("BITBUCKET_USERNAME", "")
BITBUCKET_APP_PASSWORD = cfg.get("BITBUCKET_APP_PASSWORD", "")
BITBUCKET_ACCESS_TOKEN = cfg.get("BITBUCKET_ACCESS_TOKEN", "")
BITBUCKET_WORKSPACE    = cfg.get("BITBUCKET_WORKSPACE", "")
BITBUCKET_REPO_SLUG    = cfg.get("BITBUCKET_REPO_SLUG", "")

# ── Test Jira ─────────────────────────────────────────────────────────────────
print("--- Testing Jira ---")
if not JIRA_URL or not JIRA_TOKEN:
    print("[SKIP] JIRA_URL or JIRA_API_TOKEN not set in env file.")
else:
    jira_attempts = [
        ("Basic auth v3", f"{JIRA_URL}/rest/api/3/myself", None,                                      (JIRA_USERNAME, JIRA_TOKEN)),
        ("Basic auth v2", f"{JIRA_URL}/rest/api/2/myself", None,                                      (JIRA_USERNAME, JIRA_TOKEN)),
        ("Bearer token ", f"{JIRA_URL}/rest/api/3/myself", {"Authorization": f"Bearer {JIRA_TOKEN}"}, None),
    ]

    jira_ok = False
    for label, url, headers, auth in jira_attempts:
        try:
            r = httpx.get(url, auth=auth, headers=headers or {}, timeout=10, follow_redirects=True)
            print(f"     [{label}] HTTP {r.status_code}")
            if r.status_code == 200:
                me = r.json()
                print(f"[OK] Jira connected via {label}!")
                print(f"     Logged in as : {me.get('displayName')} ({me.get('emailAddress')})")
                print(f"     Account ID   : {me.get('accountId')}")
                jira_ok = True
                break
            else:
                print(f"          Response : {r.text[:200].replace(chr(10), ' ')}")
        except Exception as e:
            print(f"     [{label}] ERROR: {e}")

    if not jira_ok:
        print("[FAIL] All Jira auth attempts failed.")

# ── Test Bitbucket ────────────────────────────────────────────────────────────
print("\n--- Testing Bitbucket ---")
if not BITBUCKET_WORKSPACE:
    print("[SKIP] BITBUCKET_WORKSPACE not set in env file.")
else:
    # Determine auth method — try username+token first (matches bitbucket_client.py)
    if BITBUCKET_ACCESS_TOKEN:
        print("     Auth method  : Basic auth (BITBUCKET_USERNAME + BITBUCKET_ACCESS_TOKEN)")
        bb_auth    = (BITBUCKET_USERNAME, BITBUCKET_ACCESS_TOKEN)
        bb_headers = {}
    elif BITBUCKET_APP_PASSWORD:
        print("     Auth method  : Basic auth (BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD)")
        bb_auth    = (BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD)
        bb_headers = {}
    else:
        print("[SKIP] No Bitbucket credentials set (BITBUCKET_ACCESS_TOKEN or BITBUCKET_APP_PASSWORD).")
        bb_auth = bb_headers = None

    if bb_auth is not None or bb_headers:
        try:
            me_resp = httpx.get(
                "https://api.bitbucket.org/2.0/user",
                auth=bb_auth, headers=bb_headers, timeout=10,
            )
            print(f"     /user status : {me_resp.status_code}")
            if me_resp.status_code == 200:
                me = me_resp.json()
                print(f"     Logged in as : {me.get('display_name')} (@{me.get('nickname','?')})")
            else:
                print(f"     /user body   : {me_resp.text[:200]}")

            repo_resp = httpx.get(
                f"https://api.bitbucket.org/2.0/repositories/{BITBUCKET_WORKSPACE}/{BITBUCKET_REPO_SLUG}",
                auth=bb_auth, headers=bb_headers, timeout=10,
            )
            print(f"     /repo status : {repo_resp.status_code}")
            if repo_resp.status_code == 200:
                data = repo_resp.json()
                print(f"[OK] Bitbucket connected!")
                print(f"     Repo        : {data['full_name']}")
                print(f"     Private     : {data.get('is_private')}")
                print(f"     Main branch : {data.get('mainbranch', {}).get('name', 'unknown')}")

                # ── Test PR creation endpoint (dry-run: will 400 if branch doesn't exist)
                print("\n     [PR Auth Test] Checking PR creation endpoint auth...")
                pr_resp = httpx.post(
                    f"https://api.bitbucket.org/2.0/repositories/{BITBUCKET_WORKSPACE}/{BITBUCKET_REPO_SLUG}/pullrequests",
                    json={
                        "title": "FORGE auth test (will fail on branch)",
                        "source": {"branch": {"name": "forge/test-does-not-exist"}},
                        "destination": {"branch": {"name": cfg.get("DEFAULT_BASE_BRANCH", "main")}},
                    },
                    auth=bb_auth, headers=bb_headers, timeout=10,
                )
                if pr_resp.status_code in (400, 422):
                    print(f"[OK] PR endpoint auth OK (HTTP {pr_resp.status_code} = branch not found, auth passed)")
                elif pr_resp.status_code == 201:
                    print("[OK] PR created (unexpected — test branch exists?)")
                elif pr_resp.status_code == 401:
                    print(f"[FAIL] PR endpoint returned 401 Unauthorized — check token has pullrequest:write scope")
                    print(f"       Response: {pr_resp.text[:300]}")
                else:
                    print(f"     PR endpoint HTTP {pr_resp.status_code}: {pr_resp.text[:200]}")
            else:
                print(f"     /repo body  : {repo_resp.text[:200]}")
                print("[FAIL] Bitbucket repo access failed.")
        except Exception as e:
            print(f"[FAIL] Bitbucket error: {e}")

print()

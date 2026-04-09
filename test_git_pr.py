"""
FORGE Git + PR Integration Test
Tests: local branch creation → commit → push to Bitbucket → PR creation
Run: python test_git_pr.py
"""
import base64
import os
import sys
import httpx
import git
from dotenv import dotenv_values
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

cfg = dotenv_values(".env")
username    = cfg.get("BITBUCKET_USERNAME", "")
token       = cfg.get("BITBUCKET_ACCESS_TOKEN", "") or cfg.get("BITBUCKET_APP_PASSWORD", "")
workspace   = cfg.get("BITBUCKET_WORKSPACE", "")
repo_slug   = cfg.get("BITBUCKET_REPO_SLUG", "")
base_branch = cfg.get("DEFAULT_BASE_BRANCH", "main")
repo_path   = cfg.get("TARGET_REPO_LOCAL_PATH", "")

auth      = (username, token)
creds     = base64.b64encode(f"{username}:{token}".encode()).decode()
push_url  = f"https://bitbucket.org/{workspace}/{repo_slug}.git"
ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
branch    = f"user/raswani/FORGE_test_{ts}"

print("=== FORGE Git + PR Integration Test ===\n")

# ── Step 1: Open local repo ───────────────────────────────────────────────────
print(f"[1] Opening repo at: {repo_path}")
try:
    repo = git.Repo(repo_path, search_parent_directories=True)
    print(f"    Root          : {repo.working_dir}")
    print(f"    Current branch: {repo.active_branch.name}")
except Exception as e:
    print(f"    FAILED: {e}")
    sys.exit(1)

# ── Step 2: Create feature branch ────────────────────────────────────────────
print(f"\n[2] Creating branch: {branch}")
try:
    repo.git.checkout(base_branch)
    repo.git.checkout("-b", branch)
    print(f"    Branch created: {repo.active_branch.name}  OK")
except Exception as e:
    print(f"    FAILED: {e}")
    sys.exit(1)

# ── Step 3: Commit a dummy file ───────────────────────────────────────────────
print(f"\n[3] Creating test commit...")
test_file = os.path.join(repo.working_dir, "FORGE_test.tmp")
try:
    with open(test_file, "w") as f:
        f.write(f"FORGE push test at {ts}\n")
    repo.index.add([test_file])
    commit = repo.index.commit(f"chore(HACPM-162535): FORGE connectivity test {ts}")
    print(f"    Commit        : {commit.hexsha[:8]}  OK")
except Exception as e:
    print(f"    FAILED: {e}")
    repo.git.checkout(base_branch)
    sys.exit(1)

# ── Step 4: Push to Bitbucket ─────────────────────────────────────────────────
print(f"\n[4] Pushing to Bitbucket...")
print(f"    URL           : https://bitbucket.org/{workspace}/{repo_slug}.git")
ssh_url = f"git@bitbucket.org:{workspace}/{repo_slug}.git"
push_ok = False
try:
    # Use SSH — avoids HTTPS credential prompts entirely.
    # Requires ~/.ssh/id_ed25519_bitbucket to be registered on the Bitbucket account.
    repo.git.push(ssh_url, branch)
    print(f"    Push          : OK  ✅")
    push_ok = True
except Exception as e:
    print(f"    Push          : FAILED  ❌")
    print(f"    Error         : {e}")

# ── Step 5: Clean up local test branch ───────────────────────────────────────
print(f"\n[5] Cleaning up local test branch...")
try:
    os.remove(test_file)
except Exception:
    pass
repo.git.checkout(base_branch)
try:
    repo.git.branch("-D", branch)
    print(f"    Local branch deleted, back on {base_branch}  OK")
except Exception:
    pass

if not push_ok:
    print("\n[6] Skipping PR creation (push failed)")
    sys.exit(1)

# ── Step 6: Create PR ─────────────────────────────────────────────────────────
print(f"\n[6] Creating PR on Bitbucket...")
payload = {
    "title": f"FORGE connectivity test {ts}",
    "description": "Auto-created by FORGE integration test. Safe to close/delete.",
    "source": {"branch": {"name": branch}},
    "destination": {"branch": {"name": base_branch}},
    "close_source_branch": True,
}
try:
    r = httpx.post(
        f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/pullrequests",
        json=payload,
        auth=auth,
        timeout=30,
    )
    if r.status_code == 201:
        pr_url = r.json()["links"]["html"]["href"]
        print(f"    PR created    : OK  ✅")
        print(f"    PR URL        : {pr_url}")
    else:
        print(f"    PR creation   : FAILED  ❌  HTTP {r.status_code}")
        print(f"    Response      : {r.text[:400]}")
except Exception as e:
    print(f"    PR creation   : FAILED  ❌  {e}")

print("\n=== Test Complete ===")

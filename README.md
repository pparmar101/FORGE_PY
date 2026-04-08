# 🚀 FORGE — AI-Powered Development Automation

> **From Jira ticket to Pull Request — fully automated.**

```
Jira Ticket → 🧠 Planner → 👨‍💻 Coder → 🔍 Reviewer → 🔀 Pull Request
                                  ↑_______________|
                                  feedback loop (max 2×)
```

---

## What is FORGE?

FORGE is a multi-agent AI system that automates the software development lifecycle. Give it a Jira ticket ID and it will analyze the requirements, write the code, review it for correctness and quality, and raise a Pull Request — all without human intervention.

The system is built around three specialized Claude AI agents that work in sequence: a **Planner** that thinks like a Senior Tech Lead, a **Coder** that writes production-quality code, and a **Reviewer** that acts as a Staff Engineer. If the Reviewer requests changes, the Coder iterates automatically before the PR is created.

---

## Architecture — The Three Agents

| Agent | Role | Input | Output |
|---|---|---|---|
| 🧠 **Planner** | Senior Tech Lead | Jira ticket (summary, description, comments) | `DeveloperNotes`, `QANotes`, `TaskBreakdown` |
| 👨‍💻 **Coder** | Senior Developer | Plan + existing repo file context | `FileChanges`, `UnitTests`, `CommitRecords` |
| 🔍 **Reviewer** | Staff Engineer | Plan + proposed code | `ReviewFeedback`, `Risks`, `FinalDecision`, `PRDetails` |

The Reviewer's `FinalDecision` is either **Approve** (PR created) or **Request Changes** (feedback sent back to Coder). The loop runs up to `MAX_CODER_ITERATIONS` times before proceeding with best-effort code.

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI Agents | [Anthropic Claude](https://anthropic.com) (`claude-sonnet-4-6`) |
| Backend API | [FastAPI](https://fastapi.tiangolo.com) + [Uvicorn](https://www.uvicorn.org) |
| Frontend UI | [Streamlit](https://streamlit.io) |
| Jira Integration | [atlassian-python-api](https://atlassian-python-api.readthedocs.io) |
| Git Operations | [GitPython](https://gitpython.readthedocs.io) |
| PR Creation | Bitbucket Cloud REST API / [PyGithub](https://pygithub.readthedocs.io) |
| HTTP Client | [httpx](https://www.python-httpx.org) |
| Data Validation | [Pydantic v2](https://docs.pydantic.dev) |
| Streaming | Server-Sent Events (SSE) via `sse-starlette` |

---

## Project Structure

```
FORGE_PY/
├── app/                           # FastAPI backend
│   ├── main.py                    # App factory, CORS, lifespan
│   ├── config.py                  # Settings loaded from .env
│   ├── agents/
│   │   ├── base.py                # BaseAgent — shared Claude client
│   │   ├── planner.py             # PlannerAgent
│   │   ├── coder.py               # CoderAgent
│   │   └── reviewer.py            # ReviewerAgent
│   ├── api/
│   │   ├── health.py              # GET /health
│   │   └── runs.py                # POST /runs, GET /runs/{id}, GET /runs/{id}/stream
│   ├── models/
│   │   ├── jira.py                # JiraTicket
│   │   ├── planner.py             # PlannerOutput, DeveloperNotes, QANotes, TaskBreakdown
│   │   ├── coder.py               # CoderOutput, FileChange, UnitTest, CommitRecord
│   │   ├── reviewer.py            # ReviewerOutput, Issue, Risk, PRDetails
│   │   └── orchestrator.py        # RunState, RunEvent, RunStatus
│   ├── orchestrator/
│   │   └── forge_orchestrator.py  # Main pipeline with feedback loop
│   └── services/
│       ├── jira_client.py         # Fetch Jira ticket
│       ├── git_service.py         # Clone, branch, apply, commit, push
│       ├── bitbucket_client.py    # Bitbucket PR creation
│       ├── github_client.py       # GitHub PR creation
│       └── pr_factory.py          # Returns correct client based on GIT_PLATFORM
├── ui/                            # Streamlit frontend
│   ├── app.py                     # Main entry point
│   ├── api_client.py              # HTTP client to FastAPI
│   └── components/
│       ├── chat_panel.py          # Live Feed tab
│       ├── agent_output.py        # Planner / Coder / Reviewer / PR tabs
│       └── run_status.py          # Progress bar
├── test_connections.py            # Credential testing utility
├── requirements.txt
└── .env.example                   # Configuration template
```

---

## Prerequisites

- Python **3.11+**
- An **Anthropic API key** — [console.anthropic.com](https://console.anthropic.com)
- A **Jira** account with API token access
- A **Bitbucket** App Password **or** **GitHub** Personal Access Token
- HTTPS access to the target git repository FORGE will work on

---

## Installation

```bash
git clone https://github.com/pparmar101/FORGE_PY.git
cd FORGE_PY

pip install -r requirements.txt

cp .env.example .env
# Open .env and fill in your credentials (see Configuration below)
```

---

## Configuration

Copy `.env.example` to `.env` and fill in the values below.

### Anthropic

| Variable | Description | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Your Claude API key (`sk-ant-...`) | ✅ |

### Jira

| Variable | Description | Required |
|---|---|---|
| `JIRA_URL` | Your Jira base URL, e.g. `https://company.jira.com` | ✅ |
| `JIRA_USERNAME` | Your Jira login email | ✅ |
| `JIRA_API_TOKEN` | Atlassian API token | ✅ |

### Git Platform

| Variable | Description | Required |
|---|---|---|
| `GIT_PLATFORM` | `bitbucket` or `github` | ✅ |

### Bitbucket *(if `GIT_PLATFORM=bitbucket`)*

| Variable | Description | Required |
|---|---|---|
| `BITBUCKET_WORKSPACE` | Workspace slug (from URL: `bitbucket.org/{workspace}/...`) | ✅ |
| `BITBUCKET_REPO_SLUG` | Repo slug (from URL: `bitbucket.org/{workspace}/{slug}`) | ✅ |
| `BITBUCKET_USERNAME` | Your Bitbucket username | ✅ |
| `BITBUCKET_APP_PASSWORD` | Bitbucket App Password | ✅ |

### GitHub *(if `GIT_PLATFORM=github`)*

| Variable | Description | Required |
|---|---|---|
| `GITHUB_TOKEN` | Personal Access Token (`ghp_...`) | ✅ |
| `GITHUB_OWNER` | GitHub org or username | ✅ |
| `GITHUB_REPO` | Repository name | ✅ |

### Target Repository

| Variable | Description | Default |
|---|---|---|
| `TARGET_REPO_URL` | HTTPS clone URL of the repo FORGE will modify | — |
| `TARGET_REPO_LOCAL_PATH` | Where to clone the repo locally | `/tmp/forge_workspace` |
| `DEFAULT_BASE_BRANCH` | Base branch for PRs | `main` |

### Model & Orchestrator

| Variable | Description | Default |
|---|---|---|
| `CLAUDE_MODEL` | Claude model to use | `claude-sonnet-4-6` |
| `CLAUDE_MAX_TOKENS` | Max tokens per agent call | `8192` |
| `MAX_CODER_ITERATIONS` | Max Coder re-runs after reviewer feedback | `2` |

### Getting Your Tokens

- **Jira API Token** → [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
- **Bitbucket App Password** → [bitbucket.org/account/settings/app-passwords](https://bitbucket.org/account/settings/app-passwords)
  - Required permissions: **Repositories** (Read + Write), **Pull requests** (Read + Write)
- **GitHub Personal Access Token** → [github.com/settings/tokens](https://github.com/settings/tokens)
  - Required scope: `repo`

---

## Running FORGE

### 1. Test your credentials

```bash
python test_connections.py
```

Both Jira and Bitbucket/GitHub should show `[OK]` before proceeding.

### 2. Start the FastAPI backend

```bash
uvicorn app.main:app --reload
```

Verify it's running: `GET http://127.0.0.1:8000/health` → `{"status": "ok"}`

### 3. Start the Streamlit UI *(new terminal)*

```bash
streamlit run ui/app.py
```

Opens at **http://localhost:8501**

### 4. Run your first automation

1. Enter a Jira ticket ID (e.g. `PROJ-123`) in the sidebar
2. Click **Run FORGE**
3. Watch the **Live Feed** tab for real-time agent progress
4. Inspect structured outputs in **Planner / Coder / Reviewer / PR** tabs
5. A PR link appears in the **PR** tab when the pipeline completes

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/runs` | Start a run — body: `{"ticket_id": "PROJ-123"}` |
| `GET` | `/runs/{id}` | Get current `RunState` snapshot |
| `GET` | `/runs/{id}/stream` | SSE stream of `RunEvent` objects |

### Run Status Flow

```
pending → fetching_ticket → planning → coding → reviewing → applying → creating_pr → complete
                                            ↑_______________|
                                            (if Request Changes)
```

---

## UI Overview

The Streamlit UI has a sidebar for input and 5 main tabs:

| Tab | Contents |
|---|---|
| 📡 **Live Feed** | Real-time stream of agent events as they happen |
| 🧠 **Planner** | Implementation plan, impacted files, QA test cases, task list |
| 👨‍💻 **Coder** | File-by-file code changes, unit tests, commit messages |
| 🔍 **Reviewer** | Review issues (by severity), risks, final decision |
| 🔀 **PR** | PR title, description, testing steps, direct link |

---

## Security Notes

- **Never commit `.env`** — it is listed in `.gitignore`
- `test_connections.py` reads credentials from `.env` at runtime — no secrets are hardcoded
- If tokens are accidentally exposed in a commit, regenerate them immediately
- Consider using short-lived tokens or scoped App Passwords with minimum required permissions

---

## License

MIT

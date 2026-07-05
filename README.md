
<p align="center">
  <img src="https://img.shields.io/badge/status-active--development-2ea44f?style=for-the-badge" alt="Status" />
  <img src="https://img.shields.io/badge/python-3.11%2B-blue?style=for-the-badge&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/license-MIT-orange?style=for-the-badge" alt="License" />
</p>

<br />

<div align="center">
  <h1>🦎 Repo Ranger</h1>
  <p><em>Navigate any codebase like you built it.</em></p>
  <br />
  <pre>curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/owner/repo"}'</pre>
</div>

---

## 📖 Overview

**Repo Ranger** is a developer tool that helps you **understand any GitHub repository** — whether you're learning a new codebase or planning to contribute. It ingests a repo (via the GitHub API, no local cloning needed), categorizes every file, breaks them into intelligent chunks, and will eventually let you **ask questions scoped strictly to the repo's own code and dependencies**.

### 🧠 Why?

Reading a fresh repository is **daunting**. LLMs help, but they:

- ❌ **Lose context** across large codebases
- ❌ **Hallucinate** solutions or explanations from unrelated code
- ❌ **Drift beyond scope** — referencing patterns, libraries, or APIs that don't exist in the repo

**Repo Ranger fixes this** by constraining every analysis strictly to the repository's own source tree and the libraries it explicitly depends on.

---

## ✨ Features

| Area | Capability |
|------|-----------|
| **🔗 URL Validation** | Parses HTTPS, SSH, and API-style GitHub URLs with branch detection |
| **📡 Web Fetch** | Pulls repo contents via GitHub API — **no `git clone` needed**, fully in-memory |
| **📂 File Separation** | Automatically categorizes files into `code`, `config`, `docs`, `binary`, `other` |
| **🧩 Intelligent Chunking** | Structure-aware splitting (AST for Python, headings for Markdown, paragraphs for others) with token budgeting |
| **🔍 Scope-Bound Q&A** | *(Planned)* Ask questions about the repo — answers are grounded only in the repo's code + its dependencies |

---

## 🏗️ Architecture (at a glance)

```
┌─────────────────────────────────────────────────────┐
│                    Client                            │
│           curl / httpx / TUI (future)               │
└──────────────┬──────────────────────────────────────┘
               │ POST /analyze { github_url }
               ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI Server (main.py)                │
├─────────────────────────────────────────────────────┤
│  validator.py  ───►  github_fetcher.py               │
│                           │                         │
│                           ▼                         │
│                    separator.py                      │
│                           │                         │
│                           ▼                         │
│                     chunker.py                       │
│                           │                         │
│                           ▼                         │
│              LLM Q&A (future phases)                │
└─────────────────────────────────────────────────────┘
```

---

## 🗂️ Project Structure

```
Repo_Ranger/
├── backend/
│   ├── main.py                  # FastAPI entry point & routes
│   ├── validator.py             # GitHub URL parser (HTTPS/SSH/API)
│   ├── separator.py             # File categorizer (code/docs/config/binary)
│   ├── chunker.py               # Token-aware + structure-aware chunking
│   ├── services/
│   │   └── github_fetcher.py    # GitHub API client (in-memory fetch)
│   └── __pycache__/
├── test/
│   ├── conftest.py              # PYTHONPATH helper for imports
│   └── test_validator.py        # 7 tests for URL validator
├── .github/workflows/
│   └── ci.yml                   # GitHub Actions: lint + test on push
├── pyproject.toml               # Ruff config + pytest config
├── requirements.txt
├── README.md
├── progress.md
└── system_design.md
```

---

## 🚀 Getting Started

```bash
# 1. Clone
git clone https://github.com/your-org/Repo_Ranger.git && cd Repo_Ranger

# 2. Create virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
uvicorn backend.main:app --reload

# 5. Use
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/psf/requests"}'
```

---

## 📚 Resources for Learning

These are the specific libraries and concepts this project uses — curated for a developer diving in:

### Core Stack

| Resource | Why |
|----------|-----|
| [FastAPI Docs](https://fastapi.tiangolo.com/learn/) | The web framework powering the API |
| [Pydantic V2](https://docs.pydantic.dev/latest/) | Request/response models & validation |
| [uvicorn](https://www.uvicorn.org/) | ASGI server to run FastAPI |
| [requests](https://requests.readthedocs.io/) | GitHub API calls |

### Chunking & NLP Concepts

| Resource | Why |
|----------|-----|
| [tiktoken](https://github.com/openai/tiktoken) | OpenAI's BPE tokenizer — used to count & budget tokens per chunk |
| [cl100k_base encoding](https://platform.openai.com/docs/guides/embeddings/embedding-models) | The token encoding used by `gpt-4` / `text-embedding-3-*` |
| [AST (Abstract Syntax Tree)](https://docs.python.org/3/library/ast.html) | Python's built-in AST — used for structure-aware Python chunking |

### GitHub API

| Resource | Why |
|----------|-----|
| [GitHub REST API - Git Trees](https://docs.github.com/en/rest/git/trees?apiVersion=2022-11-28) | Fetches the full repo file tree recursively |
| [Raw File Content](https://raw.githubusercontent.com/) | Direct content retrieval per file |
| [GitHub API - Repos](https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28) | Getting default branch & repo metadata |

### Design Patterns

| Resource | Why |
|----------|-----|
| [Pipeline Pattern](https://www.geeksforgeeks.org/pipeline-design-pattern/) | The sequential transform flow: validate → fetch → separate → chunk |
| [Dataclasses](https://docs.python.org/3/library/dataclasses.html) | Used for `ParsedGitHubURL`, `RepoData`, `FileEntry`, `RepoBucket` |
| [Frozenset for O(1) lookups](https://docs.python.org/3/library/stdtypes.html#frozenset) | Used for extension sets — fast membership checks |

---

## 📄 License

MIT

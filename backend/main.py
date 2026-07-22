from fastapi import FastAPI, HTTPException
from litellm.exceptions import (
    APIError,
    AuthenticationError,
    ContextWindowExceededError,
    RateLimitError,
)
from pydantic import BaseModel
from requests import HTTPError

from backend.chunker import chunk_all
from backend.dependency_parser import parse_dependencies
from backend.llm.provider import LLMProvider
from backend.scope_enforcer import build_context
from backend.separator import process_files
from backend.services.github_fetcher import fetch_repo
from backend.validator import InvalidGitHubURLError, validate_github_url

app = FastAPI()

# TODO: cache (owner, repo, branch) -> (chunks, dependencies, parsed) with
# short TTL so follow-up questions skip re-fetching + re-chunking.


class AnalyzeRequest(BaseModel):
    github_url: str
    github_token: str | None = None


class QueryRequest(BaseModel):
    question: str
    github_url: str
    provider: str = "openai"
    api_key: str
    model: str | None = None
    github_token: str | None = None


def _ingest_repo(github_url: str, github_token: str | None):
    """validate -> fetch -> categorize -> chunk. Raises InvalidGitHubURLError | HTTPError."""
    parsed = validate_github_url(github_url)
    repo_data = fetch_repo(parsed.owner, parsed.repo, parsed.branch, github_token)
    bucketed = process_files(repo_data.files)
    chunks = chunk_all(
        {
            "files": [
                {
                    "content": f.content,
                    "file_type": f.extension or "",
                    "file_path": f.path,
                    "relative_path": f.relative_path,
                    "category": f.category,
                    "size_bytes": f.size_bytes,
                    "is_binary": f.is_binary,
                    "binary_flag": f.binary_flag,
                }
                for f in bucketed.all_files
            ]
        }
    )
    return parsed, bucketed, chunks


@app.post("/analyze")
def analyze_repo(request: AnalyzeRequest):
    try:
        parsed, bucketed, chunks = _ingest_repo(
            request.github_url, request.github_token
        )
    except InvalidGitHubURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPError as e:
        status = e.response.status_code if e.response is not None else 502
        raise HTTPException(
            status_code=status, detail=f"GitHub API error {status}: {e}"
        )

    return {
        "owner": parsed.owner,
        "repo": parsed.repo,
        "branch": parsed.branch,
        "total_files": bucketed.total_files,
        "categories": {
            "code": len(bucketed.code),
            "config": len(bucketed.config),
            "docs": len(bucketed.docs),
            "binary": len(bucketed.binary),
            "other": len(bucketed.other),
        },
        "chunks": chunks,
    }


@app.post("/query")
async def query_repo(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    try:
        parsed, bucketed, chunks = _ingest_repo(
            request.github_url, request.github_token
        )
    except InvalidGitHubURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPError as e:
        status = e.response.status_code if e.response is not None else 502
        raise HTTPException(
            status_code=status, detail=f"GitHub API error {status}: {e}"
        )

    config_files = {f.path: f.content for f in bucketed.config if f.content}
    dependencies = parse_dependencies(config_files)

    """try:
        llm = LLMProvider(request.provider, request.api_key, request.model)
        context = build_context(chunks, dependencies, parsed.owner, parsed.repo, llm.model)
        answer = await llm.generate(request.question, context)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}")
    """

    try:
        llm = LLMProvider(request.provider, request.api_key, request.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    context = build_context(chunks, dependencies, parsed.owner, parsed.repo, llm.model)

    try:
        answer = await llm.generate(request.question, context)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (
        AuthenticationError,
        RateLimitError,
        ContextWindowExceededError,
        APIError,
    ) as e:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}")

    return {"answer": answer}

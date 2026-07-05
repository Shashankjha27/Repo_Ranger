from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from requests import HTTPError

from backend.chunker import chunk_all
from backend.separator import RepoBucket, process_files
from backend.services.github_fetcher import fetch_repo
from backend.validator import InvalidGitHubURLError, validate_github_url

app = FastAPI()


class AnalyzeRequest(BaseModel):
    github_url: str
    github_token: str | None = None


@app.post("/analyze")
def analyze_repo(request: AnalyzeRequest):
    try:
        parsed = validate_github_url(request.github_url)
    except InvalidGitHubURLError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        repo_data = fetch_repo(parsed.owner, parsed.repo, parsed.branch, request.github_token)
    except HTTPError as e:
        status = e.response.status_code if e.response is not None else 502
        raise HTTPException(status_code=status, detail=f"GitHub API error {status}: {e}")

    bucketed = process_files(repo_data.files)

    chunks = chunk_all(
        {
            "files": [
                {
                    "content": f.content,
                    "file_type": f.extension or "",
                    "path": f.path,
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

import uuid
import hashlib
import subprocess
import os
import json
import shutil

from fastapi import FastAPI, HTTPException
from pydantic  import BaseModel
from validator import validate_github_url, InvalidGitHubURLError
from separator import process_repo, RepoBucket
from chunker import chunk_all

app = FastAPI()

# First test code ---
# @app.get("/")
# def home():
#     return {"message": "Repo Ranger API"}
# @app.get("/hello")
# def agn():
#     return {"Hello": "Again"}

BASE_DIR = "cloned_repos"
CHUNKS_DIR = "chunk_store"

os.makedirs(BASE_DIR, exist_ok= True)
os.makedirs(CHUNKS_DIR, exist_ok= True)

CHUNK_STORE: dict[str, list[dict]]= {}

EXTENSION_TO_LANGUAGE = {
    ".py": "python",        ".pyw": "python",       ".pyx": "python",
    ".js": "javascript",    ".mjs": "javascript",   ".cjs": "javascript",   ".jsx": "javascript",
    ".ts": "typescript",    ".tsx": "typescript",
    ".html": "html",        ".htm": "html",
    ".css": "css",          ".scss": "scss",        ".sass": "sass",        ".less": "less",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",              ".h": "c",
    ".cpp": "cpp",          ".cc": "cpp",           ".cxx": "cpp",          ".hpp": "cpp",
    ".java": "java",
    ".kt": "kotlin",        ".kts": "kotlin",
    ".scala": "scala",
    ".rb": "ruby",          ".erb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".cs": "csharp",
    ".fs": "fsharp",        ".fsx": "fsharp",
    ".r": "r",              ".R": "r",
    ".jl": "julia",
    ".lua": "lua",
    ".sh": "shell",         ".bash": "shell",       ".zsh": "shell",        ".fish": "shell",
    ".ps1": "powershell",   ".bat": "batch",        ".cmd": "batch",
    ".sql": "sql",
    ".ex": "elixir",        ".exs": "elixir",
    ".erl": "erlang",       ".hrl": "erlang",
    ".hs": "haskell",       ".lhs": "haskell",
    ".clj": "clojure",      ".cljs": "clojure",
    ".dart": "dart",
    ".tf": "terraform",     ".tfvars": "terraform",
    ".proto": "protobuf",
    ".graphql": "graphql",  ".gql": "graphql",
    ".ipynb": "jupyter",
    ".md": "markdown",      ".mdx": "markdown",     ".rst": "restructuredtext",
    ".yaml": "yaml",        ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",        ".jsonc": "json",       ".json5": "json",
    ".xml": "xml",
    ".ini": "ini",          ".cfg": "ini",          ".conf": "ini",
    ".env": "dotenv",
}

class CloneRequest(BaseModel):
    github_url: str

def prepare_for_chunker(bucket: RepoBucket, session_id: str, repo_hash: str):
    allowed = bucket.code + bucket.config + bucket.docs + bucket.other
    files =[]
    for entry in allowed:
        ext = (entry.extension or "").lower()
        language = EXTENSION_TO_LANGUAGE.get(ext, ext)
        files.append({
            "relative_path" : entry.relative_path,
            "file_type"     : ext,
            "language"      : language,
            "content"       : entry.content,
            "session_id"    : session_id,
            "repo_hash"     : repo_hash,
        })
    return {"files" : files}

def build_stats(bucket: RepoBucket, chunks: list[dict]) -> dict:
    strategy_counts: dict[str, int] = {}
    for chunk in chunks:
        s = chunk.get("strategy", "unknown")
        strategy_counts[s] = strategy_counts.get(s,0)+1
    return {
        "total_files"           : bucket.total_files,
        "code_files"            : len(bucket.code),
        "config_files"          : len(bucket.config),
        "docs_files"            : len(bucket.docs),
        "binary_files"          : len(bucket.binary),
        "other_files"           : len(bucket.other),
        "skipped_dirs"          : len(bucket.skipped_dirs),
        "total_chunks"          : len(chunks),
        "chunks_by_strategy"    : strategy_counts,

    }

def save_chunks(session_id: str, repo_hash: str, chunks: list[dict]) -> str:
    filename = f"{session_id}__{repo_hash}.json"
    filepath = os.path.join(CHUNKS_DIR, filename)
    with open(filepath, "w", encoding = "utf-8") as f:
        json.dump (chunks, f, ensure_ascii = False, indent = 2)
    return filepath

@app.post("/clone")
def clone_repo(request: CloneRequest):

    try:
        parsed = validate_github_url(request.github_url)
    except InvalidGitHubURLError as e:
        raise HTTPException(status_code = 422, detail = str(e))

    clone_url = parsed.clone_url

    session_id = str(uuid.uuid4())
    url_hash = hashlib.sha256 (request.github_url.encode()).hexdigest()[:12]
    folder_name = f"{session_id}__{url_hash}"
    target_path = os.path.join(BASE_DIR, folder_name)


    try:
        result = subprocess.run(
            ["git", "clone", clone_url, target_path],
            capture_output=True,
            text=True,
            timeout=300
        )
    except FileNotFoundError:
        raise HTTPException (status_code= 500, detail = "Git is not installed or not in PATH")
    except subprocess.TimeoutExpired:
        if os.path.exists(target_path):
            shutil.rmtree(target_path)
        raise HTTPException (status_code=400, detail= "Git clone timed out")
    if result.returncode!= 0:
        raise HTTPException(status_code=400, detail= result.stderr)


    bucket          = process_repo(target_path)
    chunker_input   = prepare_for_chunker(bucket, session_id, url_hash)
    chunks          = chunk_all(chunker_input)

    CHUNK_STORE[session_id]  = chunks
    chunk_file_path          = save_chunks(session_id, url_hash, chunks)

    stats = build_stats(bucket, chunks)

    return {
        "session_id"            : session_id,
        "repo_hash"             : url_hash,
        "owner"                 :  parsed.owner,
        "repo"                  : parsed.repo,
        "kind"                  : parsed.kind,
        "branch"                : parsed.branch,
        "clone_path"            : target_path,
        "chunk_backup_path"     : chunk_file_path,
        "stats"                 : stats,
    }

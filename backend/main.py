import uuid
import hashlib
import subprocess
import os
from fastapi import FastAPI, HTTPException
from pydantic  import BaseModel

app = FastAPI()
# @app.get("/")
# def home():
#     return {"message": "Repo Ranger API"}
# @app.get("/hello")
# def agn():
#     return {"Hello": "Again"}

BASE_DIR = "cloned_repos"
os.makedirs(BASE_DIR, exist_ok=True)

class CloneRequest(BaseModel):
    github_url: str

@app.post("/clone")
def clone_repo(request: CloneRequest):
    session_id = str(uuid.uuid4())
    url_hash = hashlib.sha256 (request.github_url.encode()).hexdigest()[:12]
    folder_name = f"{session_id}__{url_hash}"
    target_path = os.path.join(BASE_DIR, folder_name)
    result = subprocess.run(
        ["git", "clone", request.github_url, target_path],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise HTTPException (status_code=400, detail=result.stderr)
    return {
        "session_id" : session_id,
        "url_hash" : url_hash,
        "folder" : target_path,
        "message" : "Repository  cloned successfully"
    }
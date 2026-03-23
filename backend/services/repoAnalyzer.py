from utils.github_utils import fetch_repo_data
from services.llm_service import generate_summary

def analyze_repo(repo_url):

    repo_data=fetch_repo_data(repo_url)

    files=repo_data.get("files",[])
    readme=repo_data.get("readme","")

    important_files=[
    f for f in files
    if not any(x in f for x in ["_pycache_",".git","node_modules"])
    ][:10]

    clean_data=f"""
    Important Files:
    {important_files}

    README:
    {readme}
    """

    summary=generate_summary(clean_data)

    return {
    "summary":summary
}


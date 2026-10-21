from pathlib import Path
import yaml


def _load_ci_workflow():
    ci_path = Path(".github/workflows/ci.yml")
    if not ci_path.exists():
        return None
    with open(ci_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_ci_file_parses():
    data = _load_ci_workflow()
    assert data is not None, ".github/workflows/ci.yml must exist"
    assert "jobs" in data, "Workflow must declare jobs"


def test_ci_native_matrix_os():
    data = _load_ci_workflow()
    assert data is not None
    job = data["jobs"].get("test-native") or data["jobs"].get("test")
    assert job is not None, "A native test job must be declared"
    os_list = job.get("strategy", {}).get("matrix", {}).get("os", [])
    expected = {"ubuntu-latest", "macos-latest", "windows-latest"}
    assert expected.issubset(set(os_list)), f"Missing native targets: {expected - set(os_list)}"


def test_ci_container_distros():
    data = _load_ci_workflow()
    assert data is not None
    job = data["jobs"].get("test-containers")
    assert job is not None, "Container test job must be declared"
    distros = job.get("strategy", {}).get("matrix", {}).get("distro", [])
    images = {d.get("image") for d in distros}
    assert "fedora:latest" in images, "fedora:latest container must be configured"
    assert "archlinux:base-devel" in images, "archlinux:base-devel container must be configured"


def test_ci_pyo3_manifest_and_test():
    data = _load_ci_workflow()
    assert data is not None
    pyo3_job = data["jobs"].get("pyo3-build")
    assert pyo3_job is not None, "pyo3-build job must be declared"
    steps = pyo3_job.get("steps", [])
    
    maturin_step = next((s for s in steps if "Maturin" in s.get("name", "")), None)
    assert maturin_step is not None, "Maturin build step must be declared"
    args = maturin_step.get("with", {}).get("args", "")
    assert "crates/repo_ranger_py/Cargo.toml" in args, "Manifest must point to repo_ranger_py"

    pytest_step = next((s for s in steps if "pytest" in s.get("run", "").lower()), None)
    assert pytest_step is not None, "Pytest execution step must be declared"

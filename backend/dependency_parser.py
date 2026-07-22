import configparser
import json
import re
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from pip_requirements_parser import RequirementsFile
from pyproject_parser.parsers import PEP621Parser


def parse_dependencies(files: dict[str, str]) -> dict[str, list[dict[str, str]]]:


    result: dict[str, list[dict[str, str]]] = {
        "python": [],
        "javascript": [],
        "go": [],
        "rust": [],
        "ruby": [],
        "php": [],
        "java": [],
    }

    for path, content in files.items():
        if content is None:
            continue

        filename = path.rsplit("/", 1)[-1]

        try:
            if filename == "requirements.txt":
                result["python"].extend(_parse_requirements_txt(content))
            elif filename == "pyproject.toml":
                result["python"].extend(_parse_pyproject_toml(content))
            elif filename == "setup.py":
                result["python"].extend(_parse_setup_py(content))
            elif filename == "setup.cfg":
                result["python"].extend(_parse_setup_cfg(content))
            elif filename == "Pipfile":
                result["python"].extend(_parse_pipfile(content))
            elif filename == "package.json":
                result["javascript"].extend(_parse_package_json(content))
            elif filename in ("yarn.lock", "pnpm-lock.yaml", "package-lock.json"):
                result["javascript"].append(_note_lockfile_exists(filename))
            elif filename == "go.mod":
                result["go"].extend(_parse_go_mod(content))
            elif filename == "Cargo.toml":
                result["rust"].extend(_parse_cargo_toml(content))
            elif filename == "Gemfile":
                result["ruby"].extend(_parse_gemfile(content))
            elif filename == "composer.json":
                result["php"].extend(_parse_composer_json(content))
            elif filename == "pom.xml":
                result["java"].extend(_parse_pom_xml(content))
        except Exception:
            continue

    return result


    #helpers

def _parse_pep508(dep_str: str) -> tuple[str, str]:
    dep_str = dep_str.strip().strip(",")
    if not dep_str:
        return "", ""
    try:
        req = Requirement(dep_str)
    except InvalidRequirement:
        return "", ""

    if req.url:
        return req.name, "git"

    version = str(req.specifier) if req.specifier else "*"
    return req.name, version


def _note_lockfile_exists(filename: str) -> dict[str, str]:
    return {"name": f"<{filename} present>", "version": "*"}

    #python requirements.txt

def _parse_requirements_txt(content: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    # from_string is broken in pip_requirements_parser 32.0.1 (missing Path import)
    # so we write to a temp file and use from_file instead
    tmpdir = Path(tempfile.mkdtemp())
    try:
        req_file = tmpdir / "requirements.txt"
        req_file.write_text(content, encoding="utf-8")
        rf = RequirementsFile.from_file(str(req_file), include_nested=False)
    except Exception:
        return deps
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)

    for req in rf.requirements:
        name = req.name
        if not name:
            continue

        if req.is_url:
            deps.append({"name": name, "version": "git"})
            continue

        if req.req is not None:
            version = str(req.req.specifier) if req.req.specifier else "*"
        else:
            version = "*"

        deps.append({"name": name, "version": version})
    return deps

    # pyproject.toml


def _parse_pyproject_toml(content: str) -> list[dict[str, str]]:

    data: dict[str, Any] = tomllib.loads(content)
    deps: list[dict[str, str]] = []

    project_section = data.get("project", {})
    if project_section and isinstance(project_section, dict):
        try:
            parser = PEP621Parser()
            parsed_project = parser.parse(project_section)

            for req in parsed_project.get("dependencies", []):
                name = req.name
                if req.url:
                    deps.append({"name": name, "version": "git"})
                else:
                    version = str(req.specifier) if req.specifier else "*"
                    deps.append({"name": name, "version": version})

            optional = parsed_project.get("optional-dependencies", {})
            for group_deps in optional.values():
                for req in group_deps:
                    name = req.name
                    if req.url:
                        deps.append({"name": name, "version": "git"})
                    else:
                        version = str(req.specifier) if req.specifier else "*"
                        deps.append({"name": name, "version": version})
        except Exception:
            pass

    poetry_deps = (
        data.get("tool", {}).get("poetry", {}).get("dependencies", []) or {}
    )
    for name, spec in poetry_deps.items():
        if name.lower() == "python":
            continue
        if isinstance(spec, dict):
            version = str(spec.get("version", "*"))
            if "git" in spec:
                version = "git"
        else:
            version = str(spec) if spec else "*"
        deps.append({"name": name, "version": version})
    return deps


    #setup.py/setup.cfg


def _parse_setup_py(content: str) -> list[dict[str, str]]:

    deps: list[dict[str, str]] = []

    match = re.search(r"install_requires\s*=\s*\[(.*?)\]", content, re.DOTALL)
    if not match:
        return deps

    items = re.findall(r"""['"]([^'"]+)['"]""", match.group(1))
    for item in items:
        name, version = _parse_pep508(item)
        if name:
            deps.append({"name": name, "version": version})
    return deps

def _parse_setup_cfg(content: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    parser = configparser.ConfigParser()
    parser.read_string(content)

    if not parser.has_section("options"):
        return deps

    raw = parser.get("options", "install_requires", fallback="")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        name, version = _parse_pep508(line)
        if name:
            deps.append({"name": name, "version": version})
    return deps

    #javascript package.json

def _parse_package_json(content: str) -> list[dict[str, str]]:
    data = json.loads(content)
    deps: list[dict[str, str]] = []

    for section in ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]:
        for name, version in (data.get(section, {}) or {}).items():
            deps.append({"name": name, "version": version if version else "*"})
    return deps

    #Go

_GO_REQUIRE_LINE_RE = re.compile(r"^([^\s]+)\s+(v[^\s]+)")

def _parse_go_mod(content: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    in_require_block = False

    for raw_line in content.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue

        if line == "require (":
            in_require_block = True
            continue

        if in_require_block and line == ")":
            in_require_block = False
            continue

        if in_require_block:
            match = _GO_REQUIRE_LINE_RE.match(line)
            if match:
                deps.append({"name": match.group(1), "version": match.group(2)})
        elif line.startswith("require "):
            rest = line[len("require "):].strip()
            match = _GO_REQUIRE_LINE_RE.match(rest)
            if match:
                deps.append({"name": match.group(1), "version": match.group(2)})
    return deps

    #cargo.toml

def _parse_cargo_toml(content: str) -> list[dict[str, str]]:

    data: dict[str, Any] = tomllib.loads(content)
    deps: list[dict[str, str]] = []

    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        for name, spec in (data.get(section, {}) or {}).items():
            if isinstance(spec, dict):
                version = str(spec.get("version", "*"))
                if "git" in spec:
                    version = "git"
            else:
                version = str(spec) if spec else "*"
            deps.append({"name": name, "version": version})
    return deps

    #Ruby Gemfile

_GEM_LINE_RE = re.compile(
    r"""^gem\s+['"]([^'"]+)['"](?:\s*,\s*['"]([^'"]+)['"])?"""
)

def _parse_gemfile(content: str) -> list[dict[str, str]]:

    deps: list[dict[str, str]] = []
    for raw_line in content.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line.startswith("gem "):
            continue
        match = _GEM_LINE_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        version = match.group(2) if match.group(2) else "*"
        deps.append({"name": name, "version": version})
    return deps


    #Pipfile (Pipenv)

def _parse_pipfile(content: str) -> list[dict[str, str]]:
    data: dict[str, Any] = tomllib.loads(content)
    deps: list[dict[str, str]] = []

    for section in ("packages", "dev-packages"):
        for name, spec in (data.get(section, {}) or {}).items():
            if isinstance(spec, str):
                version = spec if spec != "*" else "*"
            elif isinstance(spec, dict):
                version = str(spec.get("version", "*"))
                if spec.get("git"):
                    version = "git"
            else:
                version = "*"
            deps.append({"name": name, "version": version})
    return deps


    #composer.json (PHP)

def _parse_composer_json(content: str) -> list[dict[str, str]]:
    data = json.loads(content)
    deps: list[dict[str, str]] = []

    for section in ("require", "require-dev"):
        for name, version in (data.get(section, {}) or {}).items():
            deps.append({"name": name, "version": version if version else "*"})
    return deps


    #pom.xml (Java/Maven)

def _parse_pom_xml(content: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return deps

    ns = {"m": "http://maven.apache.org/POM/4.0.0"}

    dependencies = root.findall(".//m:dependencies/m:dependency", ns)
    if not dependencies:
        dependencies = root.findall(".//dependencies/dependency")

    for dep in dependencies:
        group = dep.find("groupId", ns)
        artifact = dep.find("artifactId", ns)
        version_el = dep.find("version", ns)

        if artifact is None:
            artifact = dep.find("artifactId")
        if group is None:
            group = dep.find("groupId")
        if version_el is None:
            version_el = dep.find("version")

        if artifact is None:
            continue

        group_id = group.text if group is not None and group.text else ""
        artifact_id = artifact.text if artifact.text else ""
        version = version_el.text if version_el is not None and version_el.text else "*"

        name = f"{group_id}:{artifact_id}" if group_id else artifact_id
        deps.append({"name": name, "version": version})
    return deps

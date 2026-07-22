from backend.dependency_parser import parse_dependencies

# ── requirements.txt ──────────────────────────────────────────────

def test_requirements_txt_basic():
    content = "requests>=2.0\nflask\n"
    result = parse_dependencies({"requirements.txt": content})
    names = [d["name"] for d in result["python"]]
    assert "requests" in names
    assert "flask" in names


def test_requirements_txt_pinned():
    content = "django==4.2.0\n"
    result = parse_dependencies({"requirements.txt": content})
    assert result["python"][0]["version"] == "==4.2.0"


def test_requirements_txt_empty():
    result = parse_dependencies({"requirements.txt": ""})
    assert result["python"] == []


def test_requirements_txt_comments_and_blanks():
    content = "# this is a comment\n\nrequests\n# another comment\nflask\n"
    result = parse_dependencies({"requirements.txt": content})
    assert len(result["python"]) == 2


def test_requirements_txt_git_url():
    content = "mylib @ git+https://github.com/user/mylib.git\n"
    result = parse_dependencies({"requirements.txt": content})
    assert result["python"][0]["version"] == "git"


# ── pyproject.toml ────────────────────────────────────────────────

def test_pyproject_toml_pep621():
    content = """
[project]
name = "myapp"
dependencies = [
    "requests>=2.0",
    "flask",
]
"""
    result = parse_dependencies({"pyproject.toml": content})
    names = [d["name"] for d in result["python"]]
    assert "requests" in names
    assert "flask" in names


def test_pyproject_toml_poetry():
    content = """
[tool.poetry.dependencies]
python = "^3.10"
django = "^4.2"
requests = ">=2.0"
"""
    result = parse_dependencies({"pyproject.toml": content})
    names = [d["name"] for d in result["python"]]
    assert "django" in names
    assert "requests" in names
    assert "python" not in names


# ── setup.py ──────────────────────────────────────────────────────

def test_setup_py():
    content = """
from setuptools import setup
setup(
    install_requires=[
        'requests>=2.0',
        'flask',
    ],
)
"""
    result = parse_dependencies({"setup.py": content})
    names = [d["name"] for d in result["python"]]
    assert "requests" in names
    assert "flask" in names


def test_setup_py_empty():
    result = parse_dependencies({"setup.py": "from setuptools import setup\nsetup()\n"})
    assert result["python"] == []


# ── setup.cfg ─────────────────────────────────────────────────────

def test_setup_cfg():
    content = """
[options]
install_requires =
    requests>=2.0
    flask
"""
    result = parse_dependencies({"setup.cfg": content})
    names = [d["name"] for d in result["python"]]
    assert "requests" in names
    assert "flask" in names


def test_setup_cfg_no_options():
    result = parse_dependencies({"setup.cfg": "[metadata]\nname = myapp\n"})
    assert result["python"] == []


# ── Pipfile ───────────────────────────────────────────────────────

def test_pipfile():
    content = """
[packages]
flask = "*"
requests = ">=2.0"
django = {git = "https://github.com/django/django.git"}

[dev-packages]
pytest = "*"
"""
    result = parse_dependencies({"Pipfile": content})
    names = [d["name"] for d in result["python"]]
    assert "flask" in names
    assert "requests" in names
    assert "pytest" in names
    django = next(d for d in result["python"] if d["name"] == "django")
    assert django["version"] == "git"


# ── package.json ──────────────────────────────────────────────────

def test_package_json_dependencies():
    content = '{"dependencies": {"react": "^18.0", "lodash": "^4.0"}}'
    result = parse_dependencies({"package.json": content})
    names = [d["name"] for d in result["javascript"]]
    assert "react" in names
    assert "lodash" in names


def test_package_json_dev_dependencies():
    content = '{"devDependencies": {"jest": "^29.0"}}'
    result = parse_dependencies({"package.json": content})
    assert result["javascript"][0]["name"] == "jest"


def test_package_json_peer_and_optional():
    content = (
        '{"peerDependencies": {"vue": "^3.0"},'
        ' "optionalDependencies": {"optional-pkg": "^1.0"}}'
    )
    result = parse_dependencies({"package.json": content})
    names = [d["name"] for d in result["javascript"]]
    assert "vue" in names
    assert "optional-pkg" in names


def test_package_json_empty():
    result = parse_dependencies({"package.json": "{}"})
    assert result["javascript"] == []


# ── lockfiles ─────────────────────────────────────────────────────

def test_yarn_lock():
    result = parse_dependencies({"yarn.lock": "some content"})
    assert len(result["javascript"]) == 1
    assert "yarn.lock" in result["javascript"][0]["name"]


def test_pnpm_lock():
    result = parse_dependencies({"pnpm-lock.yaml": "some content"})
    assert len(result["javascript"]) == 1


def test_package_lock_json():
    result = parse_dependencies({"package-lock.json": "{}"})
    assert len(result["javascript"]) == 1
    assert "package-lock.json" in result["javascript"][0]["name"]


# ── go.mod ────────────────────────────────────────────────────────

def test_go_mod_require_block():
    content = """
module github.com/user/repo

require (
    github.com/gin-gonic/gin v1.9.1
    github.com/stretchr/testify v1.8.4
)
"""
    result = parse_dependencies({"go.mod": content})
    names = [d["name"] for d in result["go"]]
    assert "github.com/gin-gonic/gin" in names
    assert "github.com/stretchr/testify" in names


def test_go_mod_single_require():
    content = "module m\nrequire github.com/pkg/errors v0.9.0\n"
    result = parse_dependencies({"go.mod": content})
    assert len(result["go"]) == 1
    assert result["go"][0]["name"] == "github.com/pkg/errors"


def test_go_mod_with_comments():
    content = "require (\n// this is a comment\n  github.com/foo/bar v1.0.0\n)\n"
    result = parse_dependencies({"go.mod": content})
    assert result["go"][0]["name"] == "github.com/foo/bar"


# ── Cargo.toml ────────────────────────────────────────────────────

def test_cargo_toml():
    content = """
[dependencies]
serde = { version = "1.0", features = ["derive"] }
tokio = "1"

[dev-dependencies]
assert_cmd = "2"
"""
    result = parse_dependencies({"Cargo.toml": content})
    names = [d["name"] for d in result["rust"]]
    assert "serde" in names
    assert "tokio" in names
    assert "assert_cmd" in names


def test_cargo_toml_git_dep():
    content = "[dependencies]\nmylib = { git = \"https://github.com/user/mylib\" }\n"
    result = parse_dependencies({"Cargo.toml": content})
    assert result["rust"][0]["version"] == "git"


# ── Gemfile ───────────────────────────────────────────────────────

def test_gemfile():
    content = """
gem "rails", "~> 7.0"
gem "rspec"
# this is a comment
gem "pg", ">= 1.0"
"""
    result = parse_dependencies({"Gemfile": content})
    names = [d["name"] for d in result["ruby"]]
    assert "rails" in names
    assert "rspec" in names
    assert "pg" in names
    rails = next(d for d in result["ruby"] if d["name"] == "rails")
    assert rails["version"] == "~> 7.0"


# ── composer.json ─────────────────────────────────────────────────

def test_composer_json():
    content = (
        '{"require": {"php": ">=8.0", "laravel/framework": "^10.0"},'
        ' "require-dev": {"phpunit/phpunit": "^10.0"}}'
    )
    result = parse_dependencies({"composer.json": content})
    names = [d["name"] for d in result["php"]]
    assert "php" in names
    assert "laravel/framework" in names
    assert "phpunit/phpunit" in names


def test_composer_json_empty():
    result = parse_dependencies({"composer.json": "{}"})
    assert result["php"] == []


# ── pom.xml ───────────────────────────────────────────────────────

def test_pom_xml():
    content = """<project>
<dependencies>
  <dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-core</artifactId>
    <version>6.1.0</version>
  </dependency>
  <dependency>
    <groupId>com.google.guava</groupId>
    <artifactId>guava</artifactId>
    <version>32.1.3-jre</version>
  </dependency>
</dependencies>
</project>"""
    result = parse_dependencies({"pom.xml": content})
    names = [d["name"] for d in result["java"]]
    assert "org.springframework:spring-core" in names
    assert "com.google.guava:guava" in names


def test_pom_xml_no_namespace():
    content = """<project>
<dependencies>
  <dependency>
    <groupId>com.foo</groupId>
    <artifactId>bar</artifactId>
    <version>1.0</version>
  </dependency>
</dependencies>
</project>"""
    result = parse_dependencies({"pom.xml": content})
    assert result["java"][0]["name"] == "com.foo:bar"


def test_pom_xml_invalid():
    result = parse_dependencies({"pom.xml": "not xml at all"})
    assert result["java"] == []


# ── edge cases ────────────────────────────────────────────────────

def test_unknown_filename():
    result = parse_dependencies({"Makefile": "all:\n\techo hello"})
    for lang_deps in result.values():
        assert lang_deps == []


def test_none_content():
    result = parse_dependencies({"requirements.txt": None})
    assert result["python"] == []


def test_empty_files_dict():
    result = parse_dependencies({})
    for lang_deps in result.values():
        assert lang_deps == []


def test_unknown_filename_ignored():
    result = parse_dependencies({
        "requirements.txt": "flask\n",
        "README.md": "# Hello",
        "Dockerfile": "FROM python:3.11",
    })
    assert len(result["python"]) == 1
    assert result["python"][0]["name"] == "flask"

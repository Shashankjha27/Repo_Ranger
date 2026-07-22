import mimetypes
import os

# import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Category = Literal["code", "config", "docs", "binary", "other"]

MAX_FILE_BYTES = 500 * 1024

_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".mypy_cache",
        "node_modules",
        ".pnp",
        ".venv",
        "venv",
        "env",
        "dist",
        "build",
        "out",
        ".next",
        ".idea",
        ".vscode",
        "coverage",
        ".nyc_output",
    }
)


_CODE_EXTS: frozenset[str] = frozenset(
    {
        ".py",
        ".pyw",
        ".pyx",
        ".pxd",
        ".js",
        ".mjs",
        ".cjs",
        ".jsx",
        ".ts",
        ".tsx",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".go",
        ".rs",
        ".c",
        ".h",
        ".cpp",
        ".cc",
        ".cxx",
        ".hpp",
        ".java",
        ".kt",
        ".kts",
        ".scala",
        ".rb",
        ".erb",
        ".rake",
        ".php",
        ".swift",
        ".m",
        ".cs",
        ".fs",
        ".fsx",
        ".vb",
        ".r",
        ".R",
        ".jl",
        ".lua",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ps1",
        ".bat",
        ".cmd",
        ".sql",
        ".plsql",
        ".ex",
        ".exs",
        ".erl",
        ".hrl",
        ".hs",
        ".lhs",
        ".clj",
        ".cljs",
        ".dart",
        ".tf",
        ".tfvars",
        ".proto",
        ".graphql",
        ".gql",
        ".ipynb",
    }
)

_CONFIG_EXTS: frozenset[str] = frozenset(
    {
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".json",
        ".jsonc",
        ".json5",
        ".xml",
        ".plist",
        ".env",
        ".env.example",
        ".env.local",
        ".lock",
        ".editorconfig",
        ".eslintrc",
        ".prettierrc",
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        ".dockerignore",
        ".npmrc",
        ".yarnrc",
        ".babelrc",
    }
)


_CONFIG_NAMES = frozenset(
    {
        "dockerfile",
        "makefile",
        "rakefile",
        "gemfile",
        "pipfile",
        "procfile",
        "vagrantfile",
        "justfile",
        "cmakelists.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "cargo.toml",
        "cargo.lock",
        "go.mod",
        "go.sum",
        "composer.json",
        "build.gradle",
        "settings.gradle",
        "pom.xml",
        ".env",
        ".env.example",
    }
)

_DOC_EXTS = frozenset(
    {
        ".md",
        ".mdx",
        ".markdown",
        ".rst",
        ".txt",
        ".adoc",
        ".asciidoc",
        ".pdf",
        ".docx",
        ".odt",
        ".tex",
        ".latex",
        ".man",
        ".changelog",
        ".license",
        ".notice",
    }
)

_DOC_NAMES = frozenset(
    {
        "readme",
        "readme.md",
        "readme.rst",
        "readme.txt",
        "changelog",
        "changelog.md",
        "license",
        "license.md",
        "license.txt",
        "contributing",
        "contributing.md",
        "authors",
        "notice",
        "patents",
        "code_of_conduct.md",
        "security.md",
    }
)

_BINARY_EXTS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".webp",
        ".svg",
        ".tiff",
        ".tif",
        ".heic",
        ".mp3",
        ".wav",
        ".ogg",
        ".flac",
        ".aac",
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".webm",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".pyc",
        ".pyo",
        ".class",
        ".o",
        ".a",
        ".so",
        ".dll",
        ".exe",
        ".wasm",
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".eot",
        ".pkl",
        ".pickle",
        ".pt",
        ".pth",
        ".h5",
        ".hdf5",
        ".onnx",
        ".parquet",
        ".feather",
        ".db",
        ".sqlite",
        ".sqlite3",
    }
)


@dataclass
class FileEntry:
    path: str
    relative_path: str
    category: Category
    extension: str
    size_bytes: int
    is_binary: bool
    content: str
    binary_flag: str

    def to_dict(self) -> dict:
        d = {
            "path": self.path,
            "relative_path": self.relative_path,
            "category": self.category,
            "size_bytes": self.size_bytes,
            "is_binary": self.is_binary,
        }
        if self.binary_flag:
            d["binary_flag"] = self.binary_flag
        return d


@dataclass
class RepoBucket:
    root: str
    code: list[FileEntry] = field(default_factory=list)
    config: list[FileEntry] = field(default_factory=list)
    docs: list[FileEntry] = field(default_factory=list)
    binary: list[FileEntry] = field(default_factory=list)
    other: list[FileEntry] = field(default_factory=list)
    skipped_dirs: list[str] = field(default_factory=list)

    @property
    def all_files(self) -> list[FileEntry]:
        return self.code + self.config + self.docs + self.binary + self.other

    @property
    def total_files(self) -> int:
        return len(self.all_files)


def _categorize(filename: str, ext: str) -> Category:
    name_lower = filename.lower()

    if ext in _BINARY_EXTS:
        return "binary"
    if name_lower in _CONFIG_NAMES:
        return "config"
    if ext in _CONFIG_EXTS:
        return "config"
    if ext in _DOC_EXTS:
        return "docs"
    if ext in _CODE_EXTS:
        return "code"
    if name_lower in _DOC_NAMES:
        return "docs"
    return "other"


def _read_content(path: Path) -> tuple[str, str]:
    mime, _ = mimetypes.guess_type(str(path))
    if mime and not (
        mime.startswith("text/")
        or mime
        in {
            "application/json",
            "application/javascript",
            "application/typescript",
            "application/xml",
            "application/x-yaml",
            "application/x-sh",
        }
    ):
        return "", f"mime:{mime}"  # FIXED

    try:
        raw = path.read_bytes()
    except Exception as exc:
        return "", f"read_error:{exc}"

    if b"\x00" in raw[:8192]:
        return "", "binary_content:null_bytes"

    try:
        return raw.decode("utf-8"), ""
    except UnicodeDecodeError:
        return "", "binary_content:decode_error"


def process_repo(root_dir: str, max_file_bytes: int = MAX_FILE_BYTES) -> RepoBucket:
    root = Path(root_dir).resolve()
    bucket = RepoBucket(root=str(root))

    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)

        pruned = []
        for d in dirnames:
            if d in _SKIP_DIRS:
                rel = str((current / d).relative_to(root))
                bucket.skipped_dirs.append(rel)
            else:
                pruned.append(d)
        dirnames[:] = pruned

        for filename in filenames:
            abs_path = current / filename  # FIX: removed ;
            rel_path = str(abs_path.relative_to(root))
            ext = abs_path.suffix.lower()

            try:
                size = abs_path.stat().st_size
            except OSError:
                continue

            category = _categorize(filename, ext)

            # CASE 1
            if size > max_file_bytes:
                bucket.binary.append(
                    FileEntry(
                        path=str(abs_path),
                        relative_path=rel_path,
                        category="binary",
                        extension=ext,
                        size_bytes=size,
                        is_binary=True,
                        content="",
                        binary_flag="too_large",  # FIXED
                    )
                )
                continue

            # CASE 2
            if category == "binary":
                bucket.binary.append(
                    FileEntry(  # FIXED
                        path=str(abs_path),
                        relative_path=rel_path,
                        category="binary",
                        extension=ext,
                        size_bytes=size,
                        is_binary=True,
                        content="",
                        binary_flag="binary_ext",
                    )
                )
                continue

            # CASE 3
            content, binary_flag = _read_content(abs_path)

            if binary_flag:
                bucket.binary.append(
                    FileEntry(
                        path=str(abs_path),
                        relative_path=rel_path,
                        category="binary",
                        extension=ext,
                        size_bytes=size,
                        is_binary=True,
                        content="",
                        binary_flag=binary_flag,
                    )
                )
                continue

            # CASE 4
            entry = FileEntry(
                path=str(abs_path),
                relative_path=rel_path,
                category=category,
                extension=ext,
                size_bytes=size,
                is_binary=False,
                content=content,
                binary_flag="",
            )
            getattr(bucket, category).append(entry)

    return bucket


def process_files(
    files: list[dict],
    repo_root: str = "",
    max_file_bytes: int = MAX_FILE_BYTES,
) -> RepoBucket:
    bucket = RepoBucket(root=repo_root)
    for f in files:
        path = f.get("path", "")
        rel_path = f.get("relative_path", path)
        content = f.get("content", "")
        size = f.get("size_bytes", len(content.encode("utf-8")))
        ext = Path(path).suffix.lower()
        filename = Path(path).name
        category = _categorize(filename, ext)

        if size > max_file_bytes:
            bucket.binary.append(
                FileEntry(
                    path=path,
                    relative_path=rel_path,
                    category="binary",
                    extension=ext,
                    size_bytes=size,
                    is_binary=True,
                    content="",
                    binary_flag="",
                )
            )
            continue
        if category == "binary":
            bucket.binary.append(
                FileEntry(
                    path=path,
                    relative_path=rel_path,
                    category="binary",
                    extension=ext,
                    size_bytes=size,
                    is_binary=True,
                    content="",
                    binary_flag="",
                )
            )
            continue

        entry = FileEntry(
            path=path,
            relative_path=rel_path,
            category=category,
            extension=ext,
            size_bytes=size,
            is_binary=False,
            content=content,
            binary_flag="",
        )
        getattr(bucket, category).append(entry)
    return bucket

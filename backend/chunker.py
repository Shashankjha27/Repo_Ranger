import re

import tiktoken
from tree_sitter_language_pack import get_parser

ENCODER = tiktoken.get_encoding("cl100k_base")

MIN_TOKEN = 200
MAX_TOKEN = 500

STRUCTURE_AWARE_TYPES = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".kt",
    ".kts",
    ".scala",
    ".swift",
    ".cs",
    ".php",
    ".rb",
    ".dart",
    ".lua",
    ".r",
    ".jl",
    ".cpp",
    ".cc",
    ".cxx",
    ".c",
    ".h",
    ".hpp",
    ".go",
    ".rs",
    ".hs",
    ".ex",
    ".exs",
    ".m",
}

_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".swift": "swift",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".dart": "dart",
    ".lua": "lua",
    ".r": "r",
    ".jl": "julia",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".hs": "haskell",
    ".ex": "elixir",
    ".exs": "elixir",
    ".m": "objc",
}

_CHUNK_NODE_TYPES = {
    "python": {"function_definition", "async_function_definition", "class_definition"},
    "javascript": {
        "function_declaration", "class_declaration",
        "method_definition", "arrow_function",
    },
    "typescript": {
        "function_declaration", "class_declaration",
        "method_definition", "arrow_function",
    },
    "java": {"method_declaration", "class_declaration"},
    "kotlin": {
        "function_declaration", "class_declaration",
        "object_declaration", "interface",
    },
    "scala": {
        "function_definition", "class_definition",
        "object_definition", "trait_definition",
    },
    "swift": {
        "function_declaration", "class_declaration",
        "struct_declaration", "protocol_declaration",
    },
    "csharp": {"class_declaration", "interface_declaration", "struct_declaration"},
    "php": {"function_definition", "class_declaration", "interface_declaration"},
    "ruby": {"method", "class", "module"},
    "dart": {"class_definition", "mixin_declaration"},
    "lua": {"function_declaration"},
    "r": {"function_definition"},
    "julia": {"function_definition", "struct_definition", "module_definition"},
    "go": {"function_declaration", "method_declaration"},
    "rust": {"function_item", "impl_item"},
    "c": {"function_definition"},
    "cpp": {"function_definition", "class_specifier"},
    "haskell": {"data_type", "bind"},
    "elixir": {"call"},
    "objc": {"function_definition", "class_interface", "class_implementation"},
}


def count_tokens(text: str) -> int:
    return len(ENCODER.encode(text))


def split_by_ast(source_code: str, file_type: str) -> tuple[list[str], str]:

    language = _LANGUAGE_MAP.get(file_type)
    if language is None:
        return [source_code], "ast_fallback"

    try:
        parser = get_parser(language)
        tree = parser.parse(source_code.encode("utf-8"))
    except Exception:
        return [source_code], "ast_fallback"

    wanted_types = _CHUNK_NODE_TYPES.get(language, set())
    lines = source_code.splitlines(keepends=True)
    covered_lines = set()
    blocks = []

    def walk(node):
        if node.type in wanted_types:
            start = node.start_point[0]
            end = node.end_point[0] + 1
            covered_lines.update(range(start, end))
            blocks.append("".join(lines[start:end]))
            return  # not descend into already captured node
        for child in node.children:
            walk(child)

    walk(tree.root_node)

    top_level = "".join(line for i, line in enumerate(lines) if i not in covered_lines)
    if top_level.strip():
        blocks.insert(0, top_level)

    if not blocks:
        return [source_code], "ast_fallback"
    return blocks, "structure_aware"


def split_markdown(text: str) -> list[str]:
    pattern = r"(?=^#{1,3} )"
    sections = re.split(pattern, text, flags=re.MULTILINE)
    return [s.strip() for s in sections if s.strip()]


def merge_small_blocks(blocks: list[str]) -> list[str]:
    merged = []
    buffer = ""
    for block in blocks:
        candidate = (buffer + "\n\n" + block).strip() if buffer else block
        if count_tokens(candidate) <= MAX_TOKEN:
            buffer = candidate
        else:
            if buffer:
                merged.append(buffer)
            buffer = block

    if buffer:
        merged.append(buffer)
    return merged


def split_large_blocks(blocks: list[str]) -> list[str]:
    result = []
    for block in blocks:
        if count_tokens(block) > MAX_TOKEN:
            tokens = ENCODER.encode(block)
            for i in range(0, len(tokens), MAX_TOKEN):
                result.append(ENCODER.decode(tokens[i : i + MAX_TOKEN]))
        else:
            result.append(block)
    return result


def build_chunk(text: str, source_meta: dict, index: int, strategy: str) -> dict:
    return {
        "text": text,
        "tokens": count_tokens(text),
        "chunk_index": index,
        "strategy": strategy,
        "source_file": source_meta.get("file_path", "")
        or source_meta.get("relative_path", ""),
        "file_type": source_meta.get("file_type", ""),
        "session_id": source_meta.get("session_id", ""),
        "repo_hash": source_meta.get("repo_hash", ""),
        "language": source_meta.get("language", ""),
    }


def chunk_file(file_obj: dict) -> list[dict]:
    content = file_obj.get("content", "")
    if not content.strip():
        return []
    file_type = file_obj.get("file_type", "").lower()
    source_meta = {
        "file_path": file_obj.get("file_path", ""),
        "file_type": file_type,
        "session_id": file_obj.get("session_id", ""),
        "repo_hash": file_obj.get("repo_hash", ""),
        "language": file_obj.get("language", ""),
    }

    if file_type == ".md":
        raw_blocks = split_markdown(content)
        strategy = "structure_aware"
    elif file_type in STRUCTURE_AWARE_TYPES:
        raw_blocks, strategy = split_by_ast(content, file_type)
    else:
        raw_blocks = [content]
        strategy = "token_split"

    merged_blocks = merge_small_blocks(raw_blocks)

    final_blocks = split_large_blocks(merged_blocks)

    chunks = []
    for i, block in enumerate(final_blocks):
        token_count = count_tokens(block)
        applied_strategy = "undersized" if token_count <= MIN_TOKEN else strategy
        chunks.append(build_chunk(block, source_meta, i, applied_strategy))
    return chunks


def chunk_all(separated: dict) -> list[dict]:

    all_chunks = []
    files = separated.get("files", [])
    for file_obj in files:
        file_chunks = chunk_file(file_obj)
        all_chunks.extend(file_chunks)
    return all_chunks

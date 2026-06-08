from typing import Any
import tiktoken
import ast
import re

ENCODER = tiktoken.get_encoding("cl100k_base")

MIN_TOKEN = 200
MAX_TOKEN = 500

STRUCTURE_AWARE_TYPES = {".py",".md",".js",".ts",".java",".cpp",".c",".go",".rs"}

def count_tokens(text:str) -> int:
    return len(ENCODER.encode(text))

def chunk_by_tokens(text: str, source_meta: dict) ->list[dict]:
    tokens = ENCODER.encode(text)
    chunks = []
    start = 0
    chunk_index = 0

    while start  < len(tokens):
        end = min(start + MAX_TOKEN, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = ENCODER.decode(chunk_tokens)
        chunks.append(build_chunk(chunk_text, source_meta,  chunk_index, "token_split"))
        chunk_index+=1
        start = end
    return chunks 


def split_python(source_code: str) -> tuple[list[str], str]:
    try:
        tree = ast.parse (source_code)
    except SyntaxError:
        return [source_code], "ast_fallback"
    
    lines = source_code.splitlines(keepends=True)
    covered_lines =  set()

    blocks = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start               = node.lineno -1
            end                 = getattr(node, "end_lineno", node.lineno)
            covered_lines.update(range(start, end))
            block               = "".join(lines[start:end])
            blocks.append(block)
    top_level = "".join(line for i, line in enumerate(lines) if i not in covered_lines)
    if top_level.strip():
        blocks.insert (0, top_level)
    if not blocks:
        return [source_code], "ast_fallback"
    return blocks, "structure_aware"

def split_markdown(text:str) -> list[str]:
    pattern = r"(?=^#{1,3} )"
    sections = re.split(pattern, text, flags=re.MULTILINE)
    return [s.strip() for s in sections if s.strip()]

def split_generic(text:str) -> list[str]:
    pattern = r"\n{2,}"
    paragraphs = re.split (pattern, text, )
    return [p.strip() for p in paragraphs if p.strip()], "structure_aware"

def merge_small_blocks (blocks: list[str]) -> list[str]:
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
                result.append(ENCODER.decode(tokens[i:i + MAX_TOKEN]))
        else: 
            result.append(block)
    return result


def build_chunk(text: str , source_meta: dict, index: int, strategy: str) -> dict:
    return {
        "text"          : text,
        "tokens"        : count_tokens(text),
        "chunk_index"   : index,
        "strategy"      : strategy,
        "source_file"   : source_meta.get("file_path") or source_meta.get("relative_path", ""),
        "file_type"     : source_meta.get("file_type",  ""),
        "session_id"    : source_meta.get("session_id", ""),
        "repo_hash"     : source_meta.get("repo_hash",  ""),
        "language"      : source_meta.get("language",   ""),
    }

def chunk_file(file_obj: dict) -> list[dict]:
    content     =   file_obj.get("content", "")
    if not content.strip():
        return []
    file_type   =   file_obj.get("file_type", "").lower()
    source_meta = {
                    "file_path"     :  file_obj.get("file_path") or file_obj.get("relative_path", ""),
                    "file_type"     :  file_type,
                    "session_id"    :  file_obj.get("session_id", ""),
                    "repo_hash"     :  file_obj.get("repo_hash", ""),
                    "language"      :  file_obj.get("language", ""),
    }

    if file_type not in STRUCTURE_AWARE_TYPES:
        return chunk_by_tokens(content, source_meta)
    
        raw_blocks, strategy = split_python(content)
    elif file_type == ".md":
        raw_blocks, strategy  = split_markdown(content), "structure_aware"
    else :
        raw_blocks, strategy  = split_generic(content)
    merged_blocks =  merge_small_blocks(raw_blocks)

    final_blocks = split_large_blocks(merged_blocks)

    chunks=[]
    for i, block in enumerate(final_blocks):
        token_count = count_tokens(block)
        applied_strategy = "undersized" if token_count < MIN_TOKEN else strategy
        chunks.append(build_chunk(block, source_meta, i, applied_strategy))
    return chunks

def chunk_all(separated: dict) -> list[dict]:
    all_chunks = []
    files = separated.get("files", [])
    for file_obj in files:
        file_chunks = chunk_file(file_obj)
        all_chunks.extend (file_chunks)
    return all_chunks



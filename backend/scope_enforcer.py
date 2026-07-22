"""
scope_enforcer.py
------------------
Builds the single "user message" string sent to the LLM, alongside
provider.py's SCOPE_SYSTEM_PROMPT. Three sections: repo header,
dependency summary, code chunks — truncated to fit the model's
context window if needed.

This module makes no LLM calls. It only builds text: dicts in,
string out. That makes it trivial to unit test without mocking
any network call.
"""

from litellm import token_counter

DEFAULT_MAX_TOKENS = 120_000


def format_header(owner: str, repo: str) -> str:
    """Section 1: repo header."""
    return f"Repository: {owner}/{repo}\n"


def format_dependencies(dependencies: dict) -> str:
    """
    Section 2: dependency summary.

    `dependencies` is the dict shape dependency_parser.parse_dependencies()
    already returns:
        {"python": [{"name": "requests", "version": "2.34.2"}, ...],
         "javascript": [...], "go": [], "rust": [], "ruby": []}

    Languages with an empty list are skipped so you don't get a
    "Ruby:" header with nothing under it.
    """
    lines = ["=== Dependencies ==="]
    for language, deps in dependencies.items():
        if not deps:
            continue
        lines.append(f"{language.capitalize()}:")
        for dep in deps:
            lines.append(f"  {dep['name']}  {dep.get('version', '*')}")
    return "\n".join(lines) + "\n"


def format_chunks(chunks: list[dict]) -> str:
    """
    Section 3: code chunks, one labeled block per chunk.

    `chunks` is the list chunker.chunk_all() already returns — each
    dict already has "source_file" and "text" from build_chunk().
    """
    lines = ["=== Code Files ==="]
    for chunk in chunks:
        lines.append(f"--- {chunk['source_file']} ---")
        lines.append(chunk["text"])
        lines.append("---")
    return "\n".join(lines) + "\n"


def _fit_to_budget(chunks: list[dict], budget: int) -> tuple[list[dict], int]:
    """
    Keep as many chunks as possible under `budget` tokens.

    Design choice, deviating slightly from "drop oldest/largest":
    sort by size ASCENDING and greedily keep adding while there's
    room. This maximizes how many different chunks (and therefore
    files) make it into context, instead of a couple of huge chunks
    eating the whole budget and starving every other file. For a
    "explain this repo" tool, breadth across files usually matters
    more than depth in one or two.

    Returns (kept_chunks_in_original_order, dropped_count).
    """
    by_size = sorted(chunks, key=lambda c: c["tokens"])
    kept = []
    running_total = 0
    for chunk in by_size:
        if running_total + chunk["tokens"] > budget:
            continue
        kept.append(chunk)
        running_total += chunk["tokens"]

    dropped = len(chunks) - len(kept)
    # put survivors back into file order so the output reads naturally
    kept.sort(key=lambda c: (c["source_file"], c["chunk_index"]))
    return kept, dropped


def build_context(
    chunks: list[dict],
    dependencies: dict,
    owner: str,
    repo: str,
    model: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """
    Assemble the full bounded context string for one /query call.

    `model` is the LiteLLM model string the caller already resolved
    via LLMProvider (e.g. self.model on your provider instance).
    It's needed here, not in chunker.py, because the actual token
    limit differs per model/provider and this is the point in the
    pipeline where the provider is finally known.
    """
    header = format_header(owner, repo)
    dep_block = format_dependencies(dependencies)

    # +50 tokens of slack reserved for the "[Truncated: ...]" note,
    # in case we end up needing to add one below.
    fixed_tokens = token_counter(model=model, text=header + dep_block) + 50
    chunk_budget = max_tokens - fixed_tokens

    total_chunk_tokens = sum(c["tokens"] for c in chunks)
    if total_chunk_tokens <= chunk_budget:
        kept_chunks, dropped = chunks, 0
    else:
        kept_chunks, dropped = _fit_to_budget(chunks, chunk_budget)

    code_block = format_chunks(kept_chunks)
    context = header + "\n" + dep_block + "\n" + code_block

    if dropped:
        kept_tokens = sum(c["tokens"] for c in kept_chunks)
        context += (
            f"\n[Truncated: showing {kept_tokens} of {total_chunk_tokens} "
            f"tokens — {dropped} chunk(s) dropped to fit context window]\n"
        )
    return context

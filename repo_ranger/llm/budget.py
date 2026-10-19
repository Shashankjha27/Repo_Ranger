from typing import Any
from urllib.parse import urlparse


class SecurityViolationError(Exception):
    pass

def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)

def is_local_url(url: str) -> bool:
    if not url:
        return True
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or not host
    except ValueError:
        return False

def is_private_repo(origin_url: str | None) -> bool:
    if not origin_url:
        return False
    cleaned = origin_url.strip().lower()
    return (
        cleaned.startswith("git@")
        or "ssh://" in cleaned
        or "internal" in cleaned
        or "gitlab.corp" in cleaned
    )

def assert_airgap_compliance(
    origin_url: str | None,
    base_url: str | None,
    strict_local: bool = False,
):
    enforce = strict_local or (
        origin_url is not None and is_private_repo(origin_url)
    )
    if enforce and base_url and not is_local_url(base_url):
        raise SecurityViolationError(
            f"Air-gap compliance violation: Remote endpoint '{base_url}' is not allowed for local/private repository under air-gap policy."
        )

class ContextBudget:

    def __init__(
        self,
        max_context_tokens: int,
        skeleton_ratio: float = 0.10,
        chunks_ratio: float = 0.60,
        history_ratio: float = 0.20,
        headroom_ratio: float = 0.10,
    ):
        if max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be positive")

        self.max_context_tokens = max_context_tokens
        self.skeleton_ratio = skeleton_ratio
        self.chunks_ratio = chunks_ratio
        self.history_ratio = history_ratio
        self.headroom_ratio = headroom_ratio

        self.skeleton_tokens = int(max_context_tokens * skeleton_ratio)
        self.chunks_tokens = int(max_context_tokens * chunks_ratio)
        self.history_tokens = int(max_context_tokens * history_ratio)
        self.headroom_tokens = int(max_context_tokens * headroom_ratio)

    def fit_chunks(
        self,
        chunks: list[dict[str, Any]],
        available_tokens: int | None = None,
    ) -> list[dict[str, Any]]:
        budget = (
            self.chunks_tokens if available_tokens is None else available_tokens
        )
        total_tokens = 0
        selected = []

        for chunk in chunks:
            content = chunk.get("content", "")
            cost = estimate_tokens(content)
            if total_tokens + cost <= budget:
                selected.append(chunk)
                total_tokens += cost
            else:
                break

        return selected

    def fit_history(
        self,
        messages: list[dict[str, str]],
        available_tokens: int | None = None,
    ) -> list[dict[str, str]]:
        budget = (
            self.history_tokens if available_tokens is None else available_tokens
        )
        selected: list[dict[str, str]] = []
        total_tokens = 0

        for msg in reversed(messages):
            cost = estimate_tokens(msg.get("content", ""))
            if total_tokens + cost <= budget:
                selected.append(msg)
                total_tokens += cost
            else:
                break

        selected.reverse()
        return selected

    def truncate_skeleton(
        self,
        skeleton: str,
        available_tokens: int | None = None,
    ) -> str:
        budget = (
            self.skeleton_tokens if available_tokens is None else available_tokens
        )
        cost = estimate_tokens(skeleton)
        if cost <= budget:
            return skeleton

        char_budget = budget * 4
        return skeleton[:char_budget]

    def build_prompt(
        self,
        skeleton: str,
        chunks: list[dict[str, Any]],
        history: list[dict[str, Any]],
        query: str,
    ) -> list[dict[str, str]]:
        clean_skeleton = self.truncate_skeleton(skeleton)
        fitted_chunks = self.fit_chunks(chunks)
        fitted_history = self.fit_history(history)

        system_selections = ["You Are an Expert Codebase Assistant."]
        if clean_skeleton:
            system_selections.append(
                f"### Repository Architecture & Symbol Skeleton:\n{clean_skeleton}"
            )
        if fitted_chunks:
            formatted_chunks = []
            for c in fitted_chunks:
                path = c.get("file_path", "unknown")
                content = c.get("content", "")
                formatted_chunks.append(f"--- File: {path} --- \n{content}")
            system_selections.append(
                "### Relevant Code Context:\n" + "\n\n".join(formatted_chunks)
            )
        system_message = {
            "role": "system",
            "content": "\n\n".join(system_selections),
        }
        prompt_messages = [system_message]
        prompt_messages.extend(fitted_history)
        prompt_messages.append({"role": "user", "content": query})

        return prompt_messages

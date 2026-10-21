import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import repo_ranger_py as rrc

from repo_ranger.llm.budget import ContextBudget, assert_airgap_compliance
from repo_ranger.llm.gateway import AIGateway

IGNORE_DIRS =  {
    ".git",
    "__pycache__",
    "node_modules",
    "target",
    ".venv",
    ".idea",
    ".vscode",
    "dist",
    "build",
}

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".zip",
    ".tar",
    ".gz",
    ".pyc",
    ".wasm",
    ".bin",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
}

class RepoSession:

    def __init__(
        self,
        gateway: AIGateway,
        budget: ContextBudget,
        origin_url: str | None = None,
        strict_local: bool = False,
        cache_dir: str | None = None,
    ):
        assert_airgap_compliance(
            origin_url= origin_url,
            base_url=gateway.base_url,
            strict_local=strict_local,
        )

        self.gateway = gateway
        self.budget = budget
        self.origin_url = origin_url
        self.strict_local = strict_local

        self.db = rrc.PyCodeDatabase()
        self.graph: rrc.PySymbolGraph | None = None
        self.merkle_tree = rrc.PyMerkleTree()
        self.cache_manager = rrc.PyCacheManager(cache_dir=cache_dir)

        self.skeleton: str = ""
        self.history: list[dict[str, str]]=[]
        self.active_working_set: set[str] = set()

    def get_merkle_root(self) -> str:
        return self.merkle_tree.root_hash()

    def get_working_set(self) -> list[str]:
        return sorted(self.active_working_set)

    def clear_history(self):
        self.history.clear()

    def ingest_files(self, files: list[tuple[str, str]]):
        for path, content in files:
            self.merkle_tree.add_file(path, content.encode("utf-8"))

        root_hash = self.merkle_tree.root_hash()
        if self.cache_manager.has(root_hash):
            cached_db = self.cache_manager.load(root_hash)
            if cached_db is not None:
                self.db = cached_db
            else:
                self.db.index(files)
                self.cache_manager.save(root_hash, self.db)
        else:
            self.db.index(files)
            self.cache_manager.save(root_hash, self.db)

        self.graph = rrc.PySymbolGraph.build(files)

        skeletons = []
        for path, content in files:
            comp = rrc.compress_ast(path, content.encode("utf-8"))
            if comp:
                skeletons.append(f"// File: {path}\n{comp}")
        self.skeleton = "\n\n".join(skeletons)

    def ingest_tarball(self, tar_gz_bytes: bytes):
        collected: list[tuple[str,str]] = []

        def callback(path: str, data: bytes):
            try:
                text = data.decode("utf-8")
                collected.append((path, text))
            except UnicodeDecodeError:
                pass

        rrc.stream_tarball(tar_gz_bytes, callback)
        self.ingest_files(collected)

    def ingest_directory(self, dir_path: str, max_file_size: int = 512 * 1024):
        collected: list[tuple[str, str]] = []
        base = Path(dir_path).resolve()

        for root, dirs, filenames in os.walk(base):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

            for name in filenames:
                suffix = Path(name).suffix.lower()
                if suffix in BINARY_EXTENSIONS:
                    continue

                full_path = Path(root) / name
                try:
                    if full_path.stat().st_size > max_file_size:
                        continue
                    rel_path = str(full_path.relative_to(base))
                    text = full_path.read_text(encoding= "utf-8", errors= "ignore")
                    collected.append((rel_path, text))
                except (OSError, UnicodeDecodeError):
                    continue
        self.ingest_files(collected)

    def search(self, query: str, limit: int = 10) -> list [dict[str, Any]]:
        raw_hits = self.db.search(query, limit)
        results = []

        for hit in raw_hits:
            self.active_working_set.add(hit.file_path)
            score = hit.score
            if self.graph:
                score += self.graph.get_pagerank(hit.file_path) * 10.0

            results.append({
                "file_path": hit.file_path,
                "content": hit.snippet,
                "score": score,
            })
        results.sort(key=lambda x:x["score"], reverse = True)
        return results

    async def ask(self, query: str, system_prompt: str = "") -> str:
        chunks = self.search(query, limit=10)
        messages = self.budget.build_prompt(
            skeleton=self.skeleton,
            chunks=chunks,
            history=self.history,
            query=query,
        )
        reply = await self.gateway.complete(
            messages=messages,
            system_prompt=system_prompt,
        )
        self.history.append({"role": "user", "content": query})
        self.history.append({"role": "assistant", "content": reply})
        return reply

    async def stream_ask(
        self, query: str, system_prompt: str = ""
    ) -> AsyncIterator[str]:
        chunks = self.search(query, limit=10)
        messages = self.budget.build_prompt(
            skeleton=self.skeleton,
            chunks=chunks,
            history=self.history,
            query=query,
        )
        tokens: list[str] = []
        async for token in self.gateway.stream_complete(
            messages=messages,
            system_prompt=system_prompt,
        ):
            tokens.append(token)
            yield token

        reply = "".join(tokens)
        self.history.append({"role": "user", "content": query})
        self.history.append({"role": "assistant", "content": reply})


"""
RAG (Retrieval-Augmented Generation) service.

Indexes source files from the repo into a ChromaDB vector store
using OpenAI embeddings, then retrieves relevant chunks at query time
to enrich both the planner and coder agent context.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

if TYPE_CHECKING:
    from app.config import Settings

# File extensions worth indexing
INDEXABLE_EXTENSIONS = {
    ".py", ".cs", ".vb", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go", ".rb", ".php", ".cpp", ".c", ".h",
    ".sql", ".sh", ".yaml", ".yml", ".json", ".xml", ".md",
}

# Skip generated / dependency directories
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "bin", "obj", "dist", "build", ".idea", ".vs", "packages",
    "TestResults", ".forge_rag",
}

CHUNK_SIZE = 80       # lines per chunk
CHUNK_OVERLAP = 10    # lines of overlap between chunks
MAX_CHUNK_CHARS = 6000  # hard cap before embedding (~1500 tokens, well under 8192)
COLLECTION_NAME = "forge_repo"
FORGE_INDEX_FILE = "FORGE_INDEX.md"


def _load_forge_index(repo_root: Path) -> tuple[list[Path] | None, list[Path] | None]:
    """
    Read FORGE_INDEX.md and return (planner_paths, coder_paths).

    Lines prefixed with 'planner:' → read directly for planner context.
    Lines prefixed with 'coder:'   → indexed into RAG for coder.
    Unprefixed lines               → treated as coder paths (backward compat).

    Returns (None, None) if no config file found.
    """
    config_file = repo_root / FORGE_INDEX_FILE
    if not config_file.exists():
        config_file = repo_root.parent / FORGE_INDEX_FILE
    if not config_file.exists():
        return None, None

    planner_paths: list[Path] = []
    coder_paths: list[Path] = []

    for line in config_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("planner:"):
            raw = line[len("planner:"):].strip()
            candidate = (repo_root.parent / raw).resolve()
            if candidate.exists():
                planner_paths.append(candidate)
        elif line.startswith("coder:"):
            raw = line[len("coder:"):].strip()
            candidate = (repo_root.parent / raw).resolve()
            if candidate.exists():
                coder_paths.append(candidate)
        else:
            # Backward compat — unprefixed lines go to coder RAG
            candidate = (repo_root.parent / line).resolve()
            if candidate.exists():
                coder_paths.append(candidate)

    return (planner_paths or None), (coder_paths or None)


def _load_index_paths(repo_root: Path) -> list[Path] | None:
    """Return coder RAG paths only (backward-compat wrapper)."""
    _, coder = _load_forge_index(repo_root)
    return coder


def load_planner_paths(repo_root: Path) -> list[Path]:
    """Return the list of folders the planner should read directly."""
    planner, _ = _load_forge_index(repo_root)
    return planner or []


class RAGService:
    def __init__(self, settings: "Settings", repo_path: str | Path) -> None:
        self._repo_path = Path(repo_path)
        self._api_key = settings.openai_api_key
        self._top_k = settings.rag_top_k

        persist_dir = str(Path(settings.target_repo_local_path) / ".forge_rag")
        self._client = chromadb.PersistentClient(path=persist_dir)

        self._embed_fn = OpenAIEmbeddingFunction(
            api_key=self._api_key,
            model_name="text-embedding-3-small",
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def index_repo(self) -> int:
        """
        Walk the configured project paths (from FORGE_INDEX.md) and upsert
        only CHANGED file chunks. Falls back to full repo walk if no config found.
        Skips files whose content hash matches what is already in ChromaDB,
        avoiding redundant OpenAI embedding API calls on unchanged files.
        Returns the number of NEW chunks upserted (0 means fully cached).
        """
        index_paths = _load_index_paths(self._repo_path)
        roots = index_paths if index_paths else [self._repo_path]

        # Build a set of all chunk IDs already stored in ChromaDB.
        # This is a single fast metadata-only fetch — no embeddings involved.
        existing_ids: set[str] = set()
        total_stored = self._collection.count()
        if total_stored > 0:
            # ChromaDB requires an explicit limit; fetch all stored IDs in one call.
            stored = self._collection.get(include=[], limit=total_stored)
            existing_ids = set(stored["ids"])

        chunks_upserted = 0
        for root in roots:
            for file_path in self._iter_source_files(root):
                chunks_upserted += self._upsert_file_if_changed(file_path, existing_ids)
        return chunks_upserted

    def query(self, text: str) -> str:
        """
        Embed `text` and return the top-K most relevant code chunks
        formatted as a string ready for inclusion in a prompt.
        """
        total = self._collection.count()
        if total == 0:
            return ""

        k = min(self._top_k, total)
        results = self._collection.query(
            query_texts=[text],
            n_results=k,
            include=["documents", "metadatas"],
        )

        parts: list[str] = []
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        for doc, meta in zip(docs, metas):
            rel_path = meta.get("rel_path", "unknown")
            chunk_idx = meta.get("chunk_idx", 0)
            parts.append(f"### {rel_path} (chunk {chunk_idx})\n```\n{doc}\n```")

        return "\n\n".join(parts)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _iter_source_files(self, root: Path):
        if root.is_file():
            # Individual file entry (e.g. HierarchyConstants.cs)
            if root.suffix.lower() in INDEXABLE_EXTENSIONS:
                yield root
            return
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                path = Path(dirpath) / fname
                if path.suffix.lower() in INDEXABLE_EXTENSIONS:
                    yield path

    def _upsert_file_if_changed(self, file_path: Path, existing_ids: set[str]) -> int:
        """
        Upsert chunks for file_path only if any chunk is new or changed.
        Chunk IDs encode a content hash, so identical content → same ID → already cached.
        Returns the number of chunks actually sent to the embedding API (0 = cache hit).
        """
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return 0

        rel_path = str(file_path.relative_to(self._repo_path))
        lines = text.splitlines()
        chunks = _split_lines(lines, CHUNK_SIZE, CHUNK_OVERLAP)

        ids, documents, metadatas = [], [], []
        for idx, chunk_lines in enumerate(chunks):
            chunk_text = "\n".join(chunk_lines)[:MAX_CHUNK_CHARS]
            chunk_hash = hashlib.md5(chunk_text.encode()).hexdigest()
            chunk_id = f"{rel_path}::chunk{idx}::{chunk_hash}"

            # Skip chunks already stored with the same content hash
            if chunk_id in existing_ids:
                continue

            ids.append(chunk_id)
            documents.append(chunk_text)
            metadatas.append({"rel_path": rel_path, "chunk_idx": idx})

        if not ids:
            return 0  # entire file unchanged — no API call made

        # Upsert only the new/changed chunks in batches
        batch_size = 50
        for i in range(0, len(ids), batch_size):
            self._collection.upsert(
                ids=ids[i:i + batch_size],
                documents=documents[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
            )
        return len(ids)


def _split_lines(
    lines: list[str], chunk_size: int, overlap: int
) -> list[list[str]]:
    """Split a list of lines into overlapping chunks."""
    if not lines:
        return []
    chunks = []
    start = 0
    while start < len(lines):
        end = min(start + chunk_size, len(lines))
        chunks.append(lines[start:end])
        if end == len(lines):
            break
        start += chunk_size - overlap
    return chunks

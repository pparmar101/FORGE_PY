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


def _load_index_paths(repo_root: Path) -> list[Path] | None:
    """
    Read FORGE_INDEX.md from the repo root and return the list of
    absolute paths to index. Returns None if no config file found
    (falls back to full repo walk).
    """
    config_file = repo_root / FORGE_INDEX_FILE
    if not config_file.exists():
        # Walk up one level (workspace may point to a sub-folder like /source)
        config_file = repo_root.parent / FORGE_INDEX_FILE
    if not config_file.exists():
        return None

    paths: list[Path] = []
    for line in config_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Paths in the file are relative to the repo root (parent of /source)
        candidate = (repo_root.parent / line).resolve()
        if candidate.exists():
            paths.append(candidate)
    return paths if paths else None


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
        changed file chunks. Falls back to full repo walk if no config found.
        Returns the number of chunks upserted.
        """
        index_paths = _load_index_paths(self._repo_path)
        if index_paths:
            roots = index_paths
        else:
            roots = [self._repo_path]

        chunks_upserted = 0
        for root in roots:
            for file_path in self._iter_source_files(root):
                chunks_upserted += self._upsert_file(file_path)
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
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                path = Path(dirpath) / fname
                if path.suffix.lower() in INDEXABLE_EXTENSIONS:
                    yield path

    def _upsert_file(self, file_path: Path) -> int:
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

            ids.append(chunk_id)
            documents.append(chunk_text)
            metadatas.append({"rel_path": rel_path, "chunk_idx": idx})

        if not ids:
            return 0

        # Upsert in batches to stay within OpenAI's 300k token/request limit
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

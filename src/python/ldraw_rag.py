"""
RAG (Retrieval-Augmented Generation) for LDraw parts and models — LlamaIndex + ChromaDB

Install dependencies:
    pip install llama-index llama-index-vector-stores-chroma chromadb openai tiktoken tqdm

For Ollama backend (local embeddings, no API key needed):
    pip install llama-index-embeddings-ollama

Set your OpenAI API key (only needed for --backend openai):
    export OPENAI_API_KEY="your-key-here"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  # Index from a directory (OpenAI embeddings, default)
  python ldraw_rag.py index <index_name> --dir ./chunks-models/

  # Index using local Ollama embeddings
  python ldraw_rag.py index <index_name> --dir ./chunks-models/ --backend nomic-embed-text:v1.5

  # Index using a custom database path
  python ldraw_rag.py index <index_name> --dir ./chunks-models/ --db ./my_db

  # Retrieve using a plain text question
  python ldraw_rag.py retrieve <index_name> "red bricks 2 studs"

  # Estimate token counts for a directory
  python ldraw_rag.py estimate --dir ./chunks-models/

NOTE: the --backend used at index time must match the one used at retrieve/query time.
"""

import argparse
import json

from pathlib import Path

import chromadb
import tiktoken
from tqdm import tqdm

from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core import StorageContext

# Prevent LlamaIndex from chunking song documents — the default 1024-token limit
# splits long models into multiple chunks, which is undesirable for this use case where each
# model should be retrieved fully or not at all
Settings.chunk_size = 10_240


# ── 1. Embed model configuration ─────────────────────────────────────────────

def _configure_embed_model(backend: str) -> None:
    """
    Set the LlamaIndex global embed model based on --backend value.

    "openai"                  → default OpenAI ada-002 (requires OPENAI_API_KEY)
    "nomic-embed-text:vX.Y"   → Ollama local model (requires ollama running locally)

    Must be called before _make_index() so the embedding model is set
    before any index or retriever is created.
    """
    if backend == "openai":
        # Leave Settings.embed_model at its default (OpenAI ada-002)
        return

    # Any other value is treated as an Ollama model tag, e.g. "nomic-embed-text:v1.5"
    try:
        from llama_index.embeddings.ollama import OllamaEmbedding
    except ImportError:
        raise SystemExit(
            "Ollama embedding backend requires: pip install llama-index-embeddings-ollama"
        )
    Settings.embed_model = OllamaEmbedding(model_name=backend)
    # nomic-embed-text and most local Ollama models have an 8192-token context limit.
    # Settings.chunk_size is measured in cl100k tokens, which diverge from nomic's tokenizer,
    # so we use 4096 (half the limit) as a safe cross-tokenizer headroom.
    Settings.chunk_size = 4_096


# ── 2. Index setup ────────────────────────────────────────────────────────────

def _make_index(collection_name: str, db_path: str) -> VectorStoreIndex:
    """Create (or reconnect to) one named ChromaDB-backed vector index."""
    chroma_client = chromadb.PersistentClient(path=db_path)
    collection    = chroma_client.get_or_create_collection(collection_name)
    vector_store  = ChromaVectorStore(chroma_collection=collection)
    storage_ctx   = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex([], storage_context=storage_ctx)

# ── 2. Indexing ───────────────────────────────────────────────────────────────

def index_directory(
    index: VectorStoreIndex,
    chunks_dir:  Path | None,
) -> None:
    """
    Populate the chunks index from the specified directory.

    chunks_dir — directory containing .chunks.md files  (chunked descriptors)

    Files that don't match pattern are silently skipped.
    """

    if chunks_dir:
        chunks_paths = sorted(p for p in chunks_dir.iterdir() if p.is_file() and p.name.endswith(".chunks.md"))
        chunks_docs  = []
        for path in chunks_paths:
            prose = path.read_text(encoding="utf-8", errors="ignore").strip()
            if prose:
                meta = {"file_path": str(path), "file_name": path.name}
                chunks_docs.append(Document(
                    text=prose,
                    id_=str(path),
                    metadata=meta,
                    excluded_embed_metadata_keys=list(meta.keys()),
                ))
        for doc in tqdm(chunks_docs, desc="Indexing chunks  ", unit="doc"):
            index.insert(doc)

        print(f"Indexed {len(chunks_docs)} chunk document(s) from '{chunks_dir}'")


# ── 5. Drop index ─────────────────────────────────────────────────────────────

def drop_index(collection_name: str, db_path: str) -> None:
    """Delete a named ChromaDB collection and all its vectors. Irreversible."""
    chroma_client = chromadb.PersistentClient(path=db_path)
    chroma_client.delete_collection(collection_name)
    print(f"Dropped index '{collection_name}' from '{db_path}'.")


# ── 6. Retrieval ──────────────────────────────────────────────────────────────

def _retrieve_with_scores(
    index: VectorStoreIndex,
    query: str,
    top_k: int,
) -> list[tuple[str, float, dict, str]]:
    """
    Retrieve top_k nodes from index and return
    [(file_name, score, metadata, text), …] sorted by descending score.
    """
    retriever = index.as_retriever(similarity_top_k=top_k)
    nodes = retriever.retrieve(query)
    results = []
    for node in nodes:
        meta  = node.metadata or {}
        score = float(node.score) if node.score is not None else 0.0
        text  = node.node.get_content()
        results.append((meta.get("file_name", "unknown"), score, meta, text))
    return results



# ── 6. Estimation ─────────────────────────────────────────────────────────────

_ENCODER = tiktoken.get_encoding("cl100k_base")


def estimate_directory(directory: Path) -> None:
    rows = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        n = len(_ENCODER.encode(path.read_text(encoding="utf-8", errors="ignore")))
        rows.append((path.name, n))

    if not rows:
        print("No files found.")
        return

    total = sum(n for _, n in rows)
    width = max(len(name) for name, _ in rows)
    for name, n in rows:
        print(f"{name:<{width}} {n:>10,} tokens {n/1_000:>8.3f} kt {n/1_000_000:>10.6f} Mt")
    print("-" * (width + 42))
    print(f"{'Total':<{width}} {total:>10,} tokens {total/1_000:>8.3f} kt {total/1_000_000:>10.6f} Mt")


# ── 7. CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAG search for LDraw parts and models.  Use 'index' command to populate indexes from directories, then 'retrieve' to query them.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    fmt = argparse.RawDescriptionHelpFormatter

    # index
    p_index = sub.add_parser(
        "index",
        help="Populate indexes from directories (creates if needed).",
        formatter_class=fmt,
        epilog=(
            "examples:\n"
            "  # dir with .chunks.md parts files\n"
            "  python ldraw_rag.py index parts --dir ./chunks-parts/\n\n"
            "  # dir with .chunks.md models files\n"
            "  python ldraw_rag.py index models --dir ./chunks-models/\n\n"
            "  # custom db path\n"
            "  python ldraw_rag.py index models --dir ./chunks-models/ --db ./my_db\n"
        ),
    )
    p_index.add_argument("index_name")
    p_index.add_argument("--dir",     metavar="DIR",     help="Directory containing .chunks.md files")
    p_index.add_argument("--db",      metavar="DB",      default="./ldraw_rag_db",
                         help="ChromaDB storage path (default: ./ldraw_rag_db)")
    p_index.add_argument("--backend", "-b", metavar="BACKEND", default="openai",
                         help="Embedding backend: 'openai' (default) or an Ollama model tag e.g. 'nomic-embed-text:v1.5'")
    p_index.add_argument("--chunk-size", type=int, default=None, metavar="N",
                         help="Override the embedding chunk size (default: 10240 for openai, 8000 for Ollama)")

    # retrieve
    p_retrieve = sub.add_parser(
        "retrieve",
        help="Return chunks",
        formatter_class=fmt,
        epilog=(
            "examples:\n"
            "  python ldraw_rag.py retrieve models \"car with windshield\" --top-k 5\n"
            "  python ldraw_rag.py retrieve parts \"brick with two studs\" --top-k 5\n"
        ),
    )
    p_retrieve.add_argument("index_name")
    p_retrieve.add_argument("question", nargs="?", default=None,
                             help="Free-text query (used for both models and parts)")
    p_retrieve.add_argument("--top-k", type=int, default=10, metavar="K")
    p_retrieve.add_argument("--metadata", "-m", action="store_true",
                             help="Output metadata JSON instead of score table")
    p_retrieve.add_argument("--scores",   "-s", action="store_true",
                             help="Show scores for chunks")
    p_retrieve.add_argument("--db",      metavar="DB",      default="./ldraw_rag_db",
                             help="ChromaDB storage path (default: ./ldraw_rag_db)")
    p_retrieve.add_argument("--backend", "-b", metavar="BACKEND", default="openai",
                             help="Embedding backend: 'openai' (default) or an Ollama model tag e.g. 'nomic-embed-text:v1.5'")

    # query
    p_query = sub.add_parser(
        "query",
        help="Query the index and display results in human-readable form.",
        formatter_class=fmt,
        epilog=(
            "examples:\n"
            "  python ldraw_rag.py query models \"beige car with windshield\" --top-k 5\n"
            "  python ldraw_rag.py query parts \"brick with two studs\" --top-k 3\n"
        ),
    )
    p_query.add_argument("index_name")
    p_query.add_argument("question")
    p_query.add_argument("--top-k", type=int, default=5, metavar="K")
    p_query.add_argument("--db", metavar="DB", default="./ldraw_rag_db",
                         help="ChromaDB storage path (default: ./ldraw_rag_db)")
    p_query.add_argument("--backend", "-b", metavar="BACKEND", default="openai",
                         help="Embedding backend: 'openai' (default) or an Ollama model tag e.g. 'nomic-embed-text:v1.5'")

    # drop
    p_drop = sub.add_parser(
        "drop",
        help="Delete an index and all its data (irreversible).",
        formatter_class=fmt,
        epilog="example:\n  python ldraw_rag.py drop models --db ./ldraw_rag_db",
    )
    p_drop.add_argument("index_name")
    p_drop.add_argument("--db", metavar="DB", default="./ldraw_rag_db",
                        help="ChromaDB storage path (default: ./ldraw_rag_db)")

    # estimate
    p_estimate = sub.add_parser("estimate", help="Estimate token counts for files in a directory.",
                                 formatter_class=fmt,
                                 epilog="example:\n  python ldraw_rag.py estimate --dir ./chunks-parts/")
    p_estimate.add_argument("--dir", metavar="DIR", required=True)

    args = parser.parse_args()

    # ── estimate (no index needed) ────────────────────────────────────────
    if args.cmd == "estimate":
        estimate_directory(Path(args.dir))
        return

    # ── drop (no index object needed) ────────────────────────────────────
    if args.cmd == "drop":
        confirm = input(f"Drop index '{args.index_name}' from '{args.db}'? This cannot be undone. [y/N] ")
        if confirm.strip().lower() == "y":
            drop_index(args.index_name, args.db)
        else:
            print("Aborted.")
        return

    _configure_embed_model(args.backend)
    if getattr(args, "chunk_size", None) is not None:
        Settings.chunk_size = args.chunk_size
    rag_index = _make_index(args.index_name, args.db)

    # ── index ─────────────────────────────────────────────────────────────
    if args.cmd == "index":
        if args.dir:
            d = Path(args.dir)
            index_directory(rag_index, chunks_dir=d)
        return

    # ── retrieve ──────────────────────────────────────────────────────────
    if args.cmd == "retrieve":
        if args.question:
            rag_query    = args.question
        else:
            p_retrieve.error("provide either a question or --file")
        
        results = _retrieve_with_scores(rag_index, rag_query, args.top_k)

        if args.metadata:
            print(json.dumps([r[2] for r in results], indent=2))
        elif args.scores:
            print("-" * 60)
            for i, r in enumerate(results, 1):
                print(f"[{i}] {r[1]:.4f}  {r[0]}")
        else:
            for i, r in enumerate(results, 1):
                print(f"[{i}] {r[0]}")


    # ── query ─────────────────────────────────────────────────────────────
    if args.cmd == "query":
        results = _retrieve_with_scores(rag_index, args.question, args.top_k)
        sep = "═" * 60
        div = "─" * 60
        for i, r in enumerate(results, 1):
            print(sep)
            print(f"[{i}] {r[0]}  (score: {r[1]:.4f})")
            print(div)
            print(r[3])
        print(sep)


if __name__ == "__main__":
    main()

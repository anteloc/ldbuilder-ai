"""
RAG (Retrieval-Augmented Generation) for LDraw parts and models — LlamaIndex + ChromaDB

Install dependencies:
    pip install llama-index llama-index-vector-stores-chroma chromadb openai tiktoken tqdm

For Ollama backend (local embeddings, no API key needed):
    pip install llama-index-embeddings-ollama

For the persistent server (serve command):
    pip install fastapi uvicorn

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

  # Start a persistent query server — eliminates cold-start for repeated queries
  python ldraw_rag.py serve --backend nomic-embed-text:v1.5 --port 8000

  # Query the server
  curl "http://localhost:8000/retrieve/models?question=red+brick&top_k=5"

NOTE: the --backend used at index time must match the one used at retrieve/query/serve time.

NOTE: existing collections were created without cosine-space HNSW settings and must be
      dropped and re-indexed to benefit from the hnsw:space=cosine correctness fix:
        python ldraw_rag.py drop <index_name>
        python ldraw_rag.py index <index_name> --dir ./chunks-.../ --backend <backend>
"""

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import chromadb

# ── Constants ─────────────────────────────────────────────────────────────────

_BACKEND_OPENAI   = "openai"                            # sentinel for the OpenAI embedding path
_CHUNKS_SUFFIX    = ".chunks.md"                        # file extension produced by the chunker
_FILE_ENCODING    = "utf-8"                             # encoding for all chunk files
_TIKTOKEN_ENC     = "cl100k_base"                       # tokeniser used for token-count estimation
_OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"  # Ollama local embedding endpoint

# ── HNSW collection settings ──────────────────────────────────────────────────
# Applied at collection creation time only. Drop + re-index existing collections
# to pick these up.
#
#   hnsw:space         = "cosine"
#       Text embeddings must be compared by cosine similarity, not the L2
#       default. This is a correctness fix: with L2, score rankings are
#       distorted for normalised embedding vectors.
#
#   hnsw:search_ef     = 50
#       ChromaDB's default is 10. With top_k=10 and ef=10, the HNSW graph
#       search has zero candidate margin, silently degrading recall quality.
#       ef=50 gives a 5× margin with negligible speed cost at ~26k vectors.
#
#   hnsw:M / hnsw:construction_ef   — kept at ChromaDB defaults.
_HNSW_SETTINGS: dict = {
    "hnsw:space":           "cosine",
    "hnsw:search_ef":       50,
    "hnsw:M":               16,
    "hnsw:construction_ef": 100,
}


# ── Result type ───────────────────────────────────────────────────────────────

class Result(NamedTuple):
    """A single retrieval hit returned by _retrieve_direct()."""
    file_name: str   # basename of the source .chunks.md file
    score:     float # similarity score: cosine → [0,1], L2 → (0,1]
    metadata:  dict  # ChromaDB metadata dict (file_path, file_name, …)
    text:      str   # full document text stored in the vector DB


# ── 1. Direct embedding ───────────────────────────────────────────────────────

@lru_cache(maxsize=512)
def _embed_query(query: str, backend: str) -> tuple[float, ...]:
    """
    Embed a query string and return a float tuple.

    Calls the embedding API directly — not through the LlamaIndex wrapper —
    to cut per-query overhead. Results are cached in-process (lru_cache):
    repeated identical queries skip the embedding call entirely, which is the
    dominant per-query cost (~100–500 ms for Ollama, ~100 ms for OpenAI).

    The tuple return type is required for lru_cache key hashability.

      Ollama  → HTTP POST _OLLAMA_EMBED_URL
      OpenAI  → openai.Embeddings.create
    """
    if backend == _BACKEND_OPENAI:
        from openai import OpenAI  # transitive dep via llama-index-llms-openai
        resp = OpenAI().embeddings.create(input=query, model="text-embedding-ada-002")
        return tuple(resp.data[0].embedding)

    # Ollama: POST {"model": "<tag>", "input": "<text>"} → {"embeddings": [[…]]}
    import urllib.request
    payload = json.dumps({"model": backend, "input": query}).encode()
    req = urllib.request.Request(
        _OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return tuple(json.loads(resp.read())["embeddings"][0])


# ── 2. ChromaDB helpers ───────────────────────────────────────────────────────

def _get_collection(collection_name: str, db_path: str) -> chromadb.Collection:
    """Return the raw ChromaDB collection — lightweight, no LlamaIndex overhead."""
    return chromadb.PersistentClient(path=db_path).get_collection(collection_name)


# ── 3. Index setup (LlamaIndex — used by 'index' command only) ────────────────

def _configure_embed_model(backend: str) -> None:
    """
    Configure the LlamaIndex global embed model and default chunk size.

    Called once at the start of the 'index' command. Not called during
    retrieve/query/serve — those embed queries directly via _embed_query()
    to avoid LlamaIndex startup and transport overhead.

    chunk_size defaults (cl100k tokens, set here as the baseline):
      openai → 10 240  (well within ada-002's context; cl100k ≈ model tokens)
      ollama → 4 096   (half of nomic-embed-text's 8192-token limit, used as a
                         cross-tokenizer safety margin: cl100k ≠ nomic tokens)

    The CLI --chunk-size flag overrides these after _make_index() returns.
    """
    from llama_index.core import Settings

    if backend == _BACKEND_OPENAI:
        Settings.chunk_size = 10_240
        return

    # Any other value is treated as an Ollama model tag, e.g. "nomic-embed-text:v1.5"
    try:
        from llama_index.embeddings.ollama import OllamaEmbedding
    except ImportError:
        raise SystemExit(
            "Ollama embedding backend requires: pip install llama-index-embeddings-ollama"
        )
    Settings.embed_model = OllamaEmbedding(model_name=backend)
    Settings.chunk_size  = 4_096


def _make_index(collection_name: str, db_path: str) -> tuple:
    """
    Wire up a ChromaDB-backed VectorStoreIndex for *indexing only*.
    Returns (VectorStoreIndex, chromadb.Collection).

    LlamaIndex is used here solely for insert_nodes() + batch embedding.
    The query path bypasses LlamaIndex entirely (see _retrieve_direct).
    chunk_size must be configured before this call via _configure_embed_model().
    """
    from llama_index.core import VectorStoreIndex, StorageContext
    from llama_index.vector_stores.chroma import ChromaVectorStore

    collection = chromadb.PersistentClient(path=db_path).get_or_create_collection(
        collection_name, metadata=_HNSW_SETTINGS
    )
    vec_store = ChromaVectorStore(chroma_collection=collection)
    storage   = StorageContext.from_defaults(vector_store=vec_store)
    return VectorStoreIndex([], storage_context=storage), collection


# ── 4. Indexing ───────────────────────────────────────────────────────────────

def index_directory(index, collection: chromadb.Collection, chunks_dir: Path, batch_size: int = 64) -> None:
    """
    Populate the vector index from _CHUNKS_SUFFIX files in chunks_dir.

    Already-indexed documents are skipped (resumable run).
    Documents are embedded and inserted in batches for efficiency.
    Files that do not end with _CHUNKS_SUFFIX are silently skipped.
    """
    from tqdm import tqdm
    from llama_index.core import Document, Settings
    from llama_index.core.node_parser import SentenceSplitter

    chunks_paths = sorted(
        p for p in chunks_dir.iterdir()
        if p.is_file() and p.name.endswith(_CHUNKS_SUFFIX)
    )

    # Fetch all IDs already present in ChromaDB to skip re-indexing
    existing_ids = set(collection.get(include=[])["ids"])

    docs = []
    for path in chunks_paths:
        if str(path) in existing_ids:
            continue
        prose = path.read_text(encoding=_FILE_ENCODING, errors="ignore").strip()
        if not prose:
            continue
        meta = {"file_path": str(path), "file_name": path.name}
        docs.append(Document(
            text=prose,
            id_=str(path),
            metadata=meta,
            excluded_embed_metadata_keys=list(meta.keys()),
        ))

    skipped = len(chunks_paths) - len(docs)
    if skipped:
        print(f"Skipping {skipped} already-indexed document(s).")

    if not docs:
        print("Nothing new to index.")
        return

    # Split documents into chunk-sized nodes, then embed and insert in batches.
    # SentenceSplitter respects Settings.chunk_size set by _configure_embed_model().
    splitter = SentenceSplitter(chunk_size=Settings.chunk_size)
    nodes    = splitter.get_nodes_from_documents(docs)

    batches = [nodes[i:i + batch_size] for i in range(0, len(nodes), batch_size)]
    with tqdm(total=len(nodes), desc="Indexing chunks", unit="node") as bar:
        for batch in batches:
            index.insert_nodes(batch)
            bar.update(len(batch))

    print(f"Indexed {len(docs)} new document(s) from '{chunks_dir}'.")


# ── 5. Drop index ─────────────────────────────────────────────────────────────

def drop_index(collection_name: str, db_path: str) -> None:
    """Delete a named ChromaDB collection and all its vectors. Irreversible."""
    chromadb.PersistentClient(path=db_path).delete_collection(collection_name)
    print(f"Dropped index '{collection_name}' from '{db_path}'.")


# ── 6. Direct retrieval (bypasses LlamaIndex) ─────────────────────────────────

def _retrieve_direct(
    collection: chromadb.Collection,
    query:      str,
    backend:    str,
    top_k:      int,
) -> list[Result]:
    """
    Embed the query and search ChromaDB directly — no LlamaIndex in the hot path.

    Replaces the old index.as_retriever() → retriever.retrieve() flow, cutting
    several abstraction layers from every query call.

    Score conversion depends on the collection's hnsw:space:
      cosine → distance = 1 − cosine_sim, so score = 1 − distance  (range ≈ [0,1])
      l2     → distance = Euclidean,      so score = 1/(1+distance) (range (0,1])
    """
    vector = list(_embed_query(query, backend))
    n      = min(top_k, collection.count())
    if n == 0:
        return []

    results = collection.query(
        query_embeddings=[vector],
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )

    space = (collection.metadata or {}).get("hnsw:space", "l2")
    out   = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        score = (1.0 - dist) if space == "cosine" else (1.0 / (1.0 + dist))
        fname = (meta or {}).get("file_name", "unknown")
        out.append(Result(file_name=fname, score=score, metadata=meta or {}, text=doc or ""))
    return out


# ── 7. Estimation ─────────────────────────────────────────────────────────────

def estimate_directory(directory: Path) -> None:
    """Print per-file and total token counts using the _TIKTOKEN_ENC tokeniser."""
    import tiktoken  # lazy — only needed for this command
    encoder = tiktoken.get_encoding(_TIKTOKEN_ENC)

    rows = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        n = len(encoder.encode(path.read_text(encoding=_FILE_ENCODING, errors="ignore")))
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


# ── 8. Serve (persistent HTTP server) ─────────────────────────────────────────

def serve(db_path: str, backend: str, host: str, port: int) -> None:
    """
    Start a persistent FastAPI server that keeps ChromaDB connections and the
    embedding cache resident in memory, eliminating cold-start overhead for
    every subsequent query.

    Collections are lazy-loaded on first request and cached in-process.
    Query embeddings are cached via _embed_query()'s lru_cache, so repeated
    identical queries skip the embedding model entirely.

    Endpoints:
      GET /retrieve/{index_name}?question=<text>[&top_k=10]
          Returns [{file_name, score, metadata, text}, …]

      GET /query/{index_name}?question=<text>[&top_k=5]
          Returns [{file_name, score, text}, …]
    """
    try:
        from fastapi import FastAPI, HTTPException
        import uvicorn
    except ImportError:
        raise SystemExit("serve command requires: pip install fastapi uvicorn")

    app         = FastAPI(title="LDraw RAG Server")
    _col_cache: dict[str, chromadb.Collection] = {}

    def _collection(name: str) -> chromadb.Collection:
        if name not in _col_cache:
            try:
                _col_cache[name] = _get_collection(name, db_path)
            except Exception as exc:
                raise HTTPException(status_code=404, detail=f"Index '{name}' not found: {exc}")
        return _col_cache[name]

    @app.get("/retrieve/{index_name}")
    def retrieve(index_name: str, question: str, top_k: int = 10):
        results = _retrieve_direct(_collection(index_name), question, backend, top_k)
        return [
            {"file_name": r.file_name, "score": r.score, "metadata": r.metadata, "text": r.text}
            for r in results
        ]

    @app.get("/query/{index_name}")
    def query(index_name: str, question: str, top_k: int = 5):
        results = _retrieve_direct(_collection(index_name), question, backend, top_k)
        return [{"file_name": r.file_name, "score": r.score, "text": r.text} for r in results]

    print(f"LDraw RAG server on http://{host}:{port}")
    print(f"  backend : {backend}")
    print(f"  database: {db_path}")
    uvicorn.run(app, host=host, port=port)


# ── 9. CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAG search for LDraw parts and models.  Use 'index' to populate indexes, then 'retrieve'/'query' to search, or 'serve' for a persistent server.",
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
    p_index.add_argument("--dir",        metavar="DIR", help="Directory containing .chunks.md files")
    p_index.add_argument("--db",         metavar="DB",  default="./ldraw_rag_db",
                         help="ChromaDB storage path (default: ./ldraw_rag_db)")
    p_index.add_argument("--backend", "-b", metavar="BACKEND", default=_BACKEND_OPENAI,
                         help="Embedding backend: 'openai' (default) or an Ollama model tag e.g. 'nomic-embed-text:v1.5'")
    p_index.add_argument("--chunk-size", type=int, default=None, metavar="N",
                         help="Override the embedding chunk size (default: 10240 for openai, 4096 for Ollama)")
    p_index.add_argument("--batch-size", type=int, default=64, metavar="N",
                         help="Number of documents per embedding batch (default: 64)")

    # retrieve
    p_retrieve = sub.add_parser(
        "retrieve",
        help="Return top-k matching chunks.",
        formatter_class=fmt,
        epilog=(
            "examples:\n"
            "  python ldraw_rag.py retrieve models \"car with windshield\" --top-k 5\n"
            "  python ldraw_rag.py retrieve parts \"brick with two studs\" --top-k 5\n"
        ),
    )
    p_retrieve.add_argument("index_name")
    p_retrieve.add_argument("question", nargs="?", default=None, help="Free-text query")
    p_retrieve.add_argument("--top-k",    type=int, default=10, metavar="K")
    p_retrieve.add_argument("--metadata", "-m", action="store_true",
                             help="Output metadata JSON instead of score table")
    p_retrieve.add_argument("--scores",   "-s", action="store_true",
                             help="Show scores for chunks")
    p_retrieve.add_argument("--db",      metavar="DB", default="./ldraw_rag_db",
                             help="ChromaDB storage path (default: ./ldraw_rag_db)")
    p_retrieve.add_argument("--backend", "-b", metavar="BACKEND", default=_BACKEND_OPENAI,
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
    p_query.add_argument("--top-k",    type=int, default=5, metavar="K")
    p_query.add_argument("--db",       metavar="DB", default="./ldraw_rag_db",
                         help="ChromaDB storage path (default: ./ldraw_rag_db)")
    p_query.add_argument("--backend",  "-b", metavar="BACKEND", default=_BACKEND_OPENAI,
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
    p_estimate = sub.add_parser(
        "estimate",
        help="Estimate token counts for files in a directory.",
        formatter_class=fmt,
        epilog="example:\n  python ldraw_rag.py estimate --dir ./chunks-parts/",
    )
    p_estimate.add_argument("--dir", metavar="DIR", required=True)

    # serve
    p_serve = sub.add_parser(
        "serve",
        help="Start a persistent HTTP server for fast repeated queries.",
        formatter_class=fmt,
        epilog=(
            "Keeps ChromaDB and the embedding cache resident in memory,\n"
            "eliminating cold-start overhead on every query.\n\n"
            "examples:\n"
            "  python ldraw_rag.py serve --backend nomic-embed-text:v1.5 --port 8000\n"
            "  curl 'http://localhost:8000/retrieve/models?question=red+brick&top_k=5'\n"
            "  curl 'http://localhost:8000/query/parts?question=2x4+brick'\n"
        ),
    )
    p_serve.add_argument("--host",    default="127.0.0.1",    help="Bind host (default: 127.0.0.1)")
    p_serve.add_argument("--port",    type=int, default=8000, help="Bind port (default: 8000)")
    p_serve.add_argument("--db",      metavar="DB", default="./ldraw_rag_db",
                         help="ChromaDB storage path (default: ./ldraw_rag_db)")
    p_serve.add_argument("--backend", "-b", metavar="BACKEND", default=_BACKEND_OPENAI,
                         help="Embedding backend: 'openai' (default) or an Ollama model tag e.g. 'nomic-embed-text:v1.5'")

    args = parser.parse_args()

    # ── estimate (no index needed) ────────────────────────────────────────────
    if args.cmd == "estimate":
        estimate_directory(Path(args.dir))
        return

    # ── drop ──────────────────────────────────────────────────────────────────
    if args.cmd == "drop":
        confirm = input(f"Drop index '{args.index_name}' from '{args.db}'? This cannot be undone. [y/N] ")
        if confirm.strip().lower() == "y":
            drop_index(args.index_name, args.db)
        else:
            print("Aborted.")
        return

    # ── serve (persistent server — no LlamaIndex needed) ──────────────────────
    if args.cmd == "serve":
        serve(args.db, args.backend, args.host, args.port)
        return

    # ── index (only command that needs LlamaIndex) ────────────────────────────
    if args.cmd == "index":
        _configure_embed_model(args.backend)
        rag_index, collection = _make_index(args.index_name, args.db)
        # CLI --chunk-size is applied last so it wins over all backend defaults
        if args.chunk_size is not None:
            from llama_index.core import Settings
            Settings.chunk_size = args.chunk_size
        if args.dir:
            index_directory(rag_index, collection, Path(args.dir), batch_size=args.batch_size)
        return

    # ── retrieve / query — direct ChromaDB path, no LlamaIndex ───────────────
    # Both commands share the collection lookup; dispatch on cmd below.
    collection = _get_collection(args.index_name, args.db)

    if args.cmd == "retrieve":
        if not args.question:
            p_retrieve.error("provide a question")
        results = _retrieve_direct(collection, args.question, args.backend, args.top_k)
        if args.metadata:
            print(json.dumps([r.metadata for r in results], indent=2))
        elif args.scores:
            print("-" * 60)
            for i, r in enumerate(results, 1):
                print(f"[{i}] {r.score:.4f}  {r.file_name}")
        else:
            for i, r in enumerate(results, 1):
                print(f"[{i}] {r.file_name}")

    elif args.cmd == "query":
        results = _retrieve_direct(collection, args.question, args.backend, args.top_k)
        sep = "═" * 60
        div = "─" * 60
        for i, r in enumerate(results, 1):
            print(sep)
            print(f"[{i}] {r.file_name}  (score: {r.score:.4f})")
            print(div)
            print(r.text)
        print(sep)


if __name__ == "__main__":
    main()

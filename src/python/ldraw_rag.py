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

import chromadb

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

      Ollama  → HTTP POST localhost:11434/api/embed
      OpenAI  → openai.Embeddings.create
    """
    if backend == "openai":
        from openai import OpenAI  # transitive dep via llama-index-llms-openai
        resp = OpenAI().embeddings.create(input=query, model="text-embedding-ada-002")
        return tuple(resp.data[0].embedding)

    # Ollama: POST {"model": "<tag>", "input": "<text>"} → {"embeddings": [[…]]}
    import urllib.request
    payload = json.dumps({"model": backend, "input": query}).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return tuple(json.loads(resp.read())["embeddings"][0])


# ── 2. ChromaDB helpers ───────────────────────────────────────────────────────

def _chroma_client(db_path: str) -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=db_path)


def _get_collection(collection_name: str, db_path: str) -> chromadb.Collection:
    """Return the raw ChromaDB collection — lightweight, no LlamaIndex overhead."""
    return _chroma_client(db_path).get_collection(collection_name)


# ── 3. Index setup (LlamaIndex — used by 'index' command only) ────────────────

def _configure_embed_model(backend: str) -> None:
    """
    Configure the LlamaIndex global embed model for the indexing path.

    Not called during retrieve/query/serve — those embed queries directly
    via _embed_query() to avoid LlamaIndex startup and transport overhead.
    """
    from llama_index.core import Settings

    if backend == "openai":
        # Leave Settings.embed_model at its default (OpenAI ada-002)
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
    # nomic-embed-text context limit is 8192 tokens; use half as a cross-tokenizer
    # safety margin (Settings.chunk_size is measured in cl100k tokens, not nomic tokens).
    Settings.chunk_size = 4_096


def _make_index(collection_name: str, db_path: str) -> tuple:
    """
    Create (or reconnect to) a ChromaDB-backed LlamaIndex for *indexing only*.
    Returns (VectorStoreIndex, chromadb.Collection).

    LlamaIndex is needed here for insert_nodes() + batch embedding during
    index time. The query path bypasses LlamaIndex entirely (_retrieve_direct).
    """
    from llama_index.core import VectorStoreIndex, StorageContext
    from llama_index.vector_stores.chroma import ChromaVectorStore

    client     = _chroma_client(db_path)
    collection = client.get_or_create_collection(collection_name, metadata=_HNSW_SETTINGS)
    vec_store  = ChromaVectorStore(chroma_collection=collection)
    storage    = StorageContext.from_defaults(vector_store=vec_store)
    return VectorStoreIndex([], storage_context=storage), collection


# ── 4. Indexing ───────────────────────────────────────────────────────────────

def index_directory(index, collection: chromadb.Collection, chunks_dir: Path | None, batch_size: int = 64) -> None:
    """
    Populate the chunks index from the specified directory.

    chunks_dir  — directory containing .chunks.md files.

    Already-indexed documents are skipped (resumable).
    Documents are embedded and inserted in batches for efficiency.
    Files that do not match the pattern are silently skipped.
    """
    if not chunks_dir:
        return

    from tqdm import tqdm
    from llama_index.core import Document, Settings
    from llama_index.core.node_parser import SentenceSplitter

    chunks_paths = sorted(
        p for p in chunks_dir.iterdir()
        if p.is_file() and p.name.endswith(".chunks.md")
    )

    # Fetch all IDs already present in ChromaDB to skip re-indexing
    existing_ids = set(collection.get(include=[])["ids"])

    docs = []
    for path in chunks_paths:
        if str(path) in existing_ids:
            continue
        prose = path.read_text(encoding="utf-8", errors="ignore").strip()
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

    # Split documents into chunk-sized nodes, respecting Settings.chunk_size
    splitter = SentenceSplitter(chunk_size=Settings.chunk_size)
    nodes    = splitter.get_nodes_from_documents(docs)

    # Insert in batches — each batch is a single embed call to the model
    batches = [nodes[i:i + batch_size] for i in range(0, len(nodes), batch_size)]
    with tqdm(total=len(nodes), desc="Indexing chunks", unit="node") as bar:
        for batch in batches:
            index.insert_nodes(batch)
            bar.update(len(batch))

    print(f"Indexed {len(docs)} new document(s) from '{chunks_dir}'.")


# ── 5. Drop index ─────────────────────────────────────────────────────────────

def drop_index(collection_name: str, db_path: str) -> None:
    """Delete a named ChromaDB collection and all its vectors. Irreversible."""
    _chroma_client(db_path).delete_collection(collection_name)
    print(f"Dropped index '{collection_name}' from '{db_path}'.")


# ── 6. Direct retrieval (bypasses LlamaIndex) ─────────────────────────────────

def _retrieve_direct(
    collection: chromadb.Collection,
    query:      str,
    backend:    str,
    top_k:      int,
) -> list[tuple[str, float, dict, str]]:
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
        out.append((fname, score, meta or {}, doc or ""))
    return out


# ── 7. Estimation ─────────────────────────────────────────────────────────────

def estimate_directory(directory: Path) -> None:
    import tiktoken  # lazy — only needed for this command
    encoder = tiktoken.get_encoding("cl100k_base")

    rows = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        n = len(encoder.encode(path.read_text(encoding="utf-8", errors="ignore")))
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
        raise SystemExit(
            "serve command requires: pip install fastapi uvicorn"
        )

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
            {"file_name": r[0], "score": r[1], "metadata": r[2], "text": r[3]}
            for r in results
        ]

    @app.get("/query/{index_name}")
    def query(index_name: str, question: str, top_k: int = 5):
        results = _retrieve_direct(_collection(index_name), question, backend, top_k)
        return [{"file_name": r[0], "score": r[1], "text": r[3]} for r in results]

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
    p_index.add_argument("--backend", "-b", metavar="BACKEND", default="openai",
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
    p_retrieve.add_argument("question", nargs="?", default=None,
                             help="Free-text query")
    p_retrieve.add_argument("--top-k",   type=int, default=10, metavar="K")
    p_retrieve.add_argument("--metadata", "-m", action="store_true",
                             help="Output metadata JSON instead of score table")
    p_retrieve.add_argument("--scores",   "-s", action="store_true",
                             help="Show scores for chunks")
    p_retrieve.add_argument("--db",      metavar="DB", default="./ldraw_rag_db",
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
    p_query.add_argument("--db",     metavar="DB", default="./ldraw_rag_db",
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
    p_serve.add_argument("--backend", "-b", metavar="BACKEND", default="openai",
                         help="Embedding backend: 'openai' (default) or an Ollama model tag e.g. 'nomic-embed-text:v1.5'")

    args = parser.parse_args()

    # ── estimate (no index needed) ────────────────────────────────────────────
    if args.cmd == "estimate":
        estimate_directory(Path(args.dir))
        return

    # ── drop (no index object needed) ─────────────────────────────────────────
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
        # CLI override is applied last so it wins over all defaults
        if getattr(args, "chunk_size", None) is not None:
            from llama_index.core import Settings
            Settings.chunk_size = args.chunk_size
        if args.dir:
            index_directory(rag_index, collection, Path(args.dir), batch_size=args.batch_size)
        return

    # ── retrieve / query — direct ChromaDB path, no LlamaIndex ───────────────
    collection = _get_collection(args.index_name, args.db)

    if args.cmd == "retrieve":
        if not args.question:
            p_retrieve.error("provide a question")

        results = _retrieve_direct(collection, args.question, args.backend, args.top_k)

        if args.metadata:
            print(json.dumps([r[2] for r in results], indent=2))
        elif args.scores:
            print("-" * 60)
            for i, r in enumerate(results, 1):
                print(f"[{i}] {r[1]:.4f}  {r[0]}")
        else:
            for i, r in enumerate(results, 1):
                print(f"[{i}] {r[0]}")

    if args.cmd == "query":
        results = _retrieve_direct(collection, args.question, args.backend, args.top_k)
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

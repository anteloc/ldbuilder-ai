"""
RAG (Retrieval-Augmented Generation) for LDraw parts and models — ChromaDB

Install dependencies:
    pip install chromadb openai tiktoken tqdm

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

NOTE: each .chunks.md file is indexed as a single unit — one embedding per file.
      The full file content is stored in ChromaDB and returned verbatim on retrieval.
      Text exceeding the model's token limit is truncated for the embedding only;
      the stored (and returned) content is always the complete file.

NOTE: existing collections were created without cosine-space HNSW settings and must be
      dropped and re-indexed to benefit from the hnsw:space=cosine correctness fix:
        python ldraw_rag.py drop <index_name>
        python ldraw_rag.py index <index_name> --dir ./chunks-.../ --backend <backend>
"""

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

import chromadb

# ── Constants ─────────────────────────────────────────────────────────────────

_BACKEND_OPENAI   = "openai"                            # sentinel for the OpenAI embedding path
_CHUNKS_SUFFIX    = ".chunks.md"                        # file extension produced by the chunker
_FILE_ENCODING    = "utf-8"                             # encoding for all chunk files
_TIKTOKEN_ENC     = "cl100k_base"                       # tokeniser used for token-count estimation (estimate cmd)
_OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"  # Ollama local embedding endpoint

# Characters fed to the embedding model at index time.
# 8 000 chars is a safe universal cap for all backends:
#   - both ada-002 and nomic-embed-text limit at ~8 192 tokens
#   - at the absolute worst case of 1 char = 1 token (e.g. pipe-heavy markdown tables),
#     8 000 chars produce at most 8 000 tokens — safely under either model's hard cap
#   - the full file content is always stored verbatim in ChromaDB for retrieval;
#     only the embedding input is capped — the returned chunk is never truncated
_EMBED_CHAR_LIMIT = 8_000

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
    metadata:  Any   # ChromaDB metadata (Mapping[str, str|int|float|bool|…]); opaque to us
    text:      str   # full document text stored in the vector DB


# ── 1. Embedding ──────────────────────────────────────────────────────────────

def _call_embed_api(text: str, backend: str) -> tuple[float, ...]:
    """
    Call the embedding API and return the vector as a float tuple.

    This is the raw API call, shared by _embed_query (cached) and
    _embed_document (uncached). Handles both backends:
      Ollama  → HTTP POST _OLLAMA_EMBED_URL
      OpenAI  → openai.Embeddings.create
    """
    if backend == _BACKEND_OPENAI:
        from openai import OpenAI  # transitive dep via llama-index-llms-openai
        resp = OpenAI().embeddings.create(input=text, model="text-embedding-ada-002")
        return tuple(resp.data[0].embedding)

    # Ollama: POST {"model": "<tag>", "input": "<text>"} → {"embeddings": [[…]]}
    import urllib.request
    import urllib.error
    payload = json.dumps({"model": backend, "input": text}).encode()
    req = urllib.request.Request(
        _OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return tuple(json.loads(resp.read())["embeddings"][0])
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"Ollama embed API {exc.code}: {body}") from exc


@lru_cache(maxsize=512)
def _embed_query(query: str, backend: str) -> tuple[float, ...]:
    """
    Embed a query string, with LRU cache for repeated identical queries.

    Caching is valuable here because the same query may be issued many times
    in a serve session (~100–500 ms per call for Ollama, ~100 ms for OpenAI).
    The tuple return type satisfies lru_cache's hashability requirement.
    """
    return _call_embed_api(query, backend)


def _embed_document(text: str, backend: str) -> tuple[float, ...]:
    """
    Embed a document string — no cache (documents are indexed once, not repeated).
    Caller is responsible for truncating text to the model's token limit beforehand.
    """
    return _call_embed_api(text, backend)


# ── 2. Embedding truncation ───────────────────────────────────────────────────

def _truncate_for_embed(text: str) -> str:
    """
    Truncate text to _EMBED_CHAR_LIMIT before embedding.

    The chunk file header (name, category, keywords, description) always
    appears first and fits well within 8 000 chars — which is the semantically
    richest part for retrieval. The full content is stored separately in
    ChromaDB and returned verbatim on retrieval; only the embedding input
    is capped here.
    """
    return text[:_EMBED_CHAR_LIMIT]


# ── 3. ChromaDB helpers ───────────────────────────────────────────────────────

def _get_collection(collection_name: str, db_path: str) -> chromadb.Collection:
    """Return the raw ChromaDB collection — lightweight, no LlamaIndex overhead."""
    return chromadb.PersistentClient(path=db_path).get_collection(collection_name)


# ── 4. Indexing ───────────────────────────────────────────────────────────────

def index_directory(
    collection: chromadb.Collection,
    chunks_dir: Path,
    backend:    str,
    batch_size: int = 64,
) -> None:
    """
    Populate the vector index from _CHUNKS_SUFFIX files in chunks_dir.

    Each .chunks.md file is stored as a single vector — one embedding per file.
    The full file content is stored verbatim in ChromaDB so retrieval always
    returns the complete file, regardless of its size.

    For files whose text exceeds the model's token limit, the embedding is
    computed on a truncated prefix; only the retrieval payload is affected
    by the full size.

    Already-indexed documents are skipped (resumable run).
    Embeddings are computed and upserted in batches for efficiency.
    Files that do not end with _CHUNKS_SUFFIX are silently skipped.
    """
    from tqdm import tqdm

    chunks_paths = sorted(
        p for p in chunks_dir.iterdir()
        if p.is_file() and p.name.endswith(_CHUNKS_SUFFIX)
    )

    # Fetch all IDs already present in ChromaDB to skip re-indexing
    existing_ids = set(collection.get(include=[])["ids"])
    new_paths    = [p for p in chunks_paths if str(p) not in existing_ids]

    skipped = len(chunks_paths) - len(new_paths)
    if skipped:
        print(f"Skipping {skipped} already-indexed document(s).")
    if not new_paths:
        print("Nothing new to index.")
        return

    batches = [new_paths[i:i + batch_size] for i in range(0, len(new_paths), batch_size)]
    indexed = 0

    with tqdm(total=len(new_paths), desc="Indexing files", unit="file") as bar:
        for batch in batches:
            ids, embeddings, documents, metadatas = [], [], [], []
            for path in batch:
                text = path.read_text(encoding=_FILE_ENCODING, errors="ignore").strip()
                if not text:
                    bar.update(1)
                    continue
                # Truncate for embedding but keep full content for storage/retrieval
                embed_text = _truncate_for_embed(text)
                vec        = list(_embed_document(embed_text, backend))
                ids.append(str(path))
                embeddings.append(vec)
                documents.append(text)                                       # full content
                metadatas.append({"file_path": str(path), "file_name": path.name})
            if ids:
                collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
                indexed += len(ids)
            bar.update(len(batch))

    print(f"Indexed {indexed} new document(s) from '{chunks_dir}'.")


# ── 5. Drop index ─────────────────────────────────────────────────────────────

def drop_index(collection_name: str, db_path: str) -> None:
    """Delete a named ChromaDB collection and all its vectors. Irreversible."""
    chromadb.PersistentClient(path=db_path).delete_collection(collection_name)
    print(f"Dropped index '{collection_name}' from '{db_path}'.")


# ── 6. Direct retrieval ───────────────────────────────────────────────────────

def _retrieve_direct(
    collection: chromadb.Collection,
    query:      str,
    backend:    str,
    top_k:      int,
) -> list[Result]:
    """
    Embed the query and search ChromaDB directly.

    Returns Result objects whose .text field contains the full .chunks.md file
    content stored at index time.

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

    assert results["documents"] is not None
    assert results["metadatas"] is not None
    assert results["distances"] is not None

    space = (collection.metadata or {}).get("hnsw:space", "l2")
    out   = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        m     = meta or {}
        score = (1.0 - dist) if space == "cosine" else (1.0 / (1.0 + dist))
        out.append(Result(file_name=str(m.get("file_name", "unknown")), score=score, metadata=m, text=doc or ""))
    return out


# ── 7. Estimation ─────────────────────────────────────────────────────────────

def estimate_directory(directory: Path) -> None:
    """Print per-file and total token counts using the cl100k_base tokeniser."""
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
          text = full .chunks.md file content

      GET /query/{index_name}?question=<text>[&top_k=5]
          Returns [{file_name, score, text}, …]
          text = full .chunks.md file content
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
    p_index.add_argument("--batch-size", type=int, default=64, metavar="N",
                         help="Number of documents per embedding batch (default: 64)")

    # retrieve
    p_retrieve = sub.add_parser(
        "retrieve",
        help="Return top-k matching chunk files.",
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

    # ── serve (persistent server) ─────────────────────────────────────────────
    if args.cmd == "serve":
        serve(args.db, args.backend, args.host, args.port)
        return

    # ── index ─────────────────────────────────────────────────────────────────
    if args.cmd == "index":
        collection = chromadb.PersistentClient(path=args.db).get_or_create_collection(
            args.index_name, metadata=_HNSW_SETTINGS
        )
        if args.dir:
            index_directory(collection, Path(args.dir), args.backend, batch_size=args.batch_size)
        return

    # ── retrieve / query — direct ChromaDB path ───────────────────────────────
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

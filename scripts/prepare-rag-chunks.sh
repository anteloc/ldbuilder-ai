#!/bin/bash

source "$(dirname "$0")/common.sh"

prepare_rag_db="$1"
models_max_size="$2"
models_chunks_dir="$3"
parts_chunks_dir="$4"

if [ -z "$prepare_rag_db" ] || [ -z "$parts_chunks_dir" ] || [ -z "$models_chunks_dir" ] || [ -z "$models_max_size" ]; then
  echo "Usage: $(basename "$0") <prepare-rag-db> <models-max-size-kb> <models-chunks-dir> <parts-chunks-dir>"
  echo "Prepares the RAG chunks (.md documents) for the parts and models, to be added to a vector database."
  echo "prepare-rag-db: the output of prepare-rag-models.sh script."
  echo "models-max-size-kb: the maximum size of the models to be included in the RAG chunks (in kilobytes)."
  echo "models-chunks-dir: the output directory for the models chunks .md files."
  echo "parts-chunks-dir: the output directory for the parts chunks .md files."
  echo "Example: $(basename "$0") /some/path/prepare-rag.db 100 /some/path/models-chunks /some/path/parts-chunks"
  echo "The contents for the output dirs will be:"
  echo "models-chunks/"
  echo "  10001-1.mpd.chunks.md"
  echo "  10025-1_Mail-Car.mpd.chunks.md"
  echo "  ..."
  echo "parts-chunks/"
  echo "  3821d07.dat.chunks.md"
  echo "  6148.dat.chunks.md"
  echo "  ..."
  exit 1
fi

# Verify that the db exists
if [ ! -f "$prepare_rag_db" ]; then
  echo "Error: File '$prepare_rag_db' does not exist."
  exit 1
fi

set -euo pipefail

prepare_rag_db="$(realpath "$prepare_rag_db")"

# create output dirs if they don't exist
mkdir -p "$models_chunks_dir"
mkdir -p "$parts_chunks_dir"



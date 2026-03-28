#!/bin/bash

source "$(dirname "$0")/common.sh"

prepare_rag_db="$1"
models_chunks_dir="$2"
parts_chunks_dir="$3"

if [ -z "$prepare_rag_db" ] || [ -z "$parts_chunks_dir" ] || [ -z "$models_chunks_dir" ]; then
  echo "Usage: $(basename "$0") <prepare-rag-db> <models-chunks-dir> <parts-chunks-dir>"
  echo "Prepares the RAG chunks (.md documents) for the parts and models, to be added to a vector database."
  echo "prepare-rag-db: the output of prepare-rag-models.sh script."
  echo "models-chunks-dir: the output directory for the models chunks .md files."
  echo "parts-chunks-dir: the output directory for the parts chunks .md files."
  echo "Example: $(basename "$0") /some/path/prepare-rag.db /some/path/models-chunks /some/path/parts-chunks"
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

### Parts chunks
part_chunk_tmpl="Name: %s
Description: %s
Dimensions: %s LDU
"
sqlite-utils query "$prepare_rag_db" "select name, description, dim_x, dim_y, dim_z from VW_PART_INFOS_BBOXES ;" --tsv --no-headers \
    | grep -v '^s\\' \
    | tr -d '\r' \
    | while IFS=$'\t' read -r p_name p_des dim_x dim_y dim_z; do
        dims="$(printf "%.01f x %.01f x %.01f" "$dim_x" "$dim_y" "$dim_z" | sed -E 's/\.0[ ]?/ /g')"
        chunk_content="$(printf "$part_chunk_tmpl" "$p_name" "$p_des" "$dims")"
        echo "$chunk_content" > "$parts_chunks_dir/${p_name}.chunks.md"
    done

### Models chunks
# alias   category        description     keywords        num_parts       difficulty      size_kb

model_chunk_tmpl="Name: %s
Category: %s
Description: %s
Keywords: %s
Number of parts: %d
Difficulty: %s
"

sqlite-utils query "$prepare_rag_db" "select alias as name, category, description, keywords, num_parts, difficulty from VW_MODEL_INFOS ;" --tsv --no-headers \
    | tr -d '\r' \
    | while IFS=$'\t' read -r p_name p_category p_des p_keywords p_num_parts p_difficulty p_size_kb; do
        chunk_content="$(printf "$model_chunk_tmpl" "$p_name" "$p_category" "$p_des" "$p_keywords" "$p_num_parts" "$p_difficulty")"
        echo "$chunk_content" > "$models_chunks_dir/${p_name}.chunks.md"
    done
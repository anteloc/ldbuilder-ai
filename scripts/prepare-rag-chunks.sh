#!/bin/bash

source "$(dirname "$0")/common.sh"

function tabulate() {
python -c '
import sys
from tabulate import tabulate

rows = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue

    # Split by "|" and clean cells
    parts = [cell.strip() for cell in line.split("|")]
    parts = [p for p in parts if p != ""]

    rows.append(parts)

if not rows:
    print("No data to tabulate.", file=sys.stderr)
    sys.exit(0)

# First row = headers
headers = rows[0]
data = rows[1:]

# Normalize row lengths
max_cols = len(headers)
data = [row + [""] * (max_cols - len(row)) for row in data]

print(tabulate(data, headers=headers, tablefmt="github"))
'
}

function bom() {
    local model_filename="$1"
    local annotated_model="$annotated_models_dir/$model_filename"
    
    echo "| Qty | Description | Color | Name |"

    cat "$annotated_model" \
        | grep -v '0 !TOUCHES' \
        | grep -A 1 '0 !P' \
        | cut -d "'" -f2,4 \
        | sed "s/'/ | /" \
        | sed '/--/d' \
        | awk 'NR % 2 == 0 {for(i=15; i<=NF; i++) printf "%s ", $i; printf "\n"; next}; { printf "| %s | ", $0 }' \
        | sort \
        | uniq -c \
        | awk '{printf "| %s \n", $0 }'

}

prepare_rag_db="$1"
annotated_models_dir="$2"
models_chunks_dir="$3"
parts_chunks_dir="$4"

if [ -z "$prepare_rag_db" ] || [ -z "$annotated_models_dir" ] || [ -z "$parts_chunks_dir" ] || [ -z "$models_chunks_dir" ]; then
  echo "Usage: $(basename "$0") <prepare-rag-db> <annotated-models-dir> <models-chunks-dir> <parts-chunks-dir>"
  echo "Prepares the RAG chunks (.md documents) for the parts and models, to be added to a vector database."
  echo "prepare-rag-db: the output of prepare-rag-models.sh script."
  echo "annotated-models-dir: the directory containing annotated model files."
  echo "models-chunks-dir: the output directory for the models chunks .md files."
  echo "parts-chunks-dir: the output directory for the parts chunks .md files."
  echo "Example: $(basename "$0") /some/path/prepare-rag.db /some/path/annotated-models /some/path/models-chunks /some/path/parts-chunks"
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

# Verify that the annotated models dir exists
if [ ! -d "$annotated_models_dir" ]; then
  echo "Error: Directory '$annotated_models_dir' does not exist."
  exit 1
fi

set -euo pipefail

# create output dirs if they don't exist
mkdir -p "$models_chunks_dir"
mkdir -p "$parts_chunks_dir"

prepare_rag_db="$(realpath "$prepare_rag_db")"
annotated_models_dir="$(realpath "$annotated_models_dir")"
models_chunks_dir="$(realpath "$models_chunks_dir")"
parts_chunks_dir="$(realpath "$parts_chunks_dir")"

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

**Parts BOM:**

%s
"

sqlite-utils query "$prepare_rag_db" "select alias as name, category, description, keywords, num_parts, difficulty from VW_MODEL_INFOS ;" --tsv --no-headers \
    | tr -d '\r' \
    | while IFS=$'\t' read -r p_name p_category p_des p_keywords p_num_parts p_difficulty ; do
        parts_bom="$(bom "$p_name" | tabulate)"
        chunk_content="$(printf "$model_chunk_tmpl" "$p_name" "$p_category" "$p_des" "$p_keywords" "$p_num_parts" "$p_difficulty" "$parts_bom")"
        echo "$chunk_content" > "$models_chunks_dir/${p_name}.chunks.md"
    done

# cat rag-models/10022-1_Dining-Car.mpd | grep -v '0 !TOUCHES' | grep -A 1 '0 !P' | cut -d "'" -f2,4 | sed "s|'|, |" | sed '/--/d' | awk 'NR % 2 == 0 {for(i=15; i<=NF; i++) printf "%s ", $i; printf "\n"; next}; { printf "of: %s, ", $0 }' | sort | uniq -c
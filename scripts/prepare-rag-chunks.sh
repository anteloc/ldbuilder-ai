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

    # output a BOM table, with fields (including headers) separated by "|", in order to be tabulated and nicely formatted later by tabulate()
    echo "| Qty | Description | Color | Dimensions (LDU) | Name |"

    cat "$annotated_model" \
        | grep -v '0 !TOUCHES' \
        | grep -A 1 '0 !P' \
        | sed '/--/d' \
        | sed -E \
            -e "s/^.*'([^']+)' *'([^']+)'.* (([0-9]+(\.[0-9]+)?x[0-9]+(\.[0-9]+)?x[0-9]+(\.[0-9]+)?)|N\/A) LDU$/ | \1 | \2 | \3 /" \
            -e 's/^([0-9.-]+[[:space:]]+){14}//' \
        | awk 'NR % 2 != 0 { printf "%s", $0 }; NR % 2 == 0 { printf "| %s | \n", $0 }' \
        | sort \
        | uniq -c \
        | awk '{printf "| %s \n", $0 }'

}

model_chunk_tmpl="Name: %s
Category: %s
Keywords: %s
Description: %s
Difficulty: %s
Number of parts: %d

**Parts BOM:**

%s
"

function chunk_models() {
    local target_dir="$1"

    sqlite-utils query "$prepare_rag_db" "select alias as name, category, description, keywords, num_parts, difficulty from VW_MODEL_INFOS ;" --tsv --no-headers \
        | tr -d '\r' \
        | while IFS=$'\t' read -r p_name p_category p_des p_keywords p_num_parts p_difficulty ; do
            echo "Processing model: $p_name" >&2
            parts_bom="$(bom "$p_name" | tabulate)"
            chunk_content="$(printf "$model_chunk_tmpl" "$p_name" "$p_category" "$p_keywords" "$p_des" "$p_difficulty" "$p_num_parts" "$parts_bom")"
            echo "$chunk_content" > "$target_dir/${p_name}.chunks.md"
        done
}

function parts_by_model_table() {
    # from all the model chunk files, extract all parts infos used by each model
    # and append them as records to an output a table with fields: 
    # model name, model keywords, part description, part dimensions, part name (.dat filename)
    local table_file="$1"
    local m_chunks_dir="$2"

    # row: model name, model keywords, part description, part dimensions, part name (.dat filename)
    printf "model\tkeywords\tdescription\tdimensions\tname\n" > "$table_file"

    for c in "$m_chunks_dir"/*.chunks.md; do
        model_name="$(basename "$c" .chunks.md)"
        kws="$(cat "$c" | grep Keywords | sed 's/Keywords: //; s/LEGO//g')"

        cat "$c" \
        | awk '$0 == "**Parts BOM:**" {output="true"; next}; output == "true" {print $0}' \
        | tail +4 \
        | awk -v model="$model_name" -v kws="$kws" -F '|' '
            function trim(s) { 
                gsub(/^[ \t]+|[ \t]+$/, "", s)
                return s
            }
            {
                printf "%s\t%s\t%s\t%s\t%s\n", trim(model), trim(kws), trim($3), trim($5), trim($6)
            }
        ' \
        | grep -i -v '.ldr' \
        | sort -u
    done | sort >> "$table_file"

}

function parts_infos_kws_table() {
    # from a table with fields (model name, model keywords, part description, part dimensions, part name),
    # create a new table containing only records for parts, with fields:
    # name, description, dimensions, keywords
    # **NOTE:** the keywords field is an **aggregation** of all model keywords that use that part, in order to tag parts with meaningful keywords
    # i.e. model uses part X and has keywords A, B, C -> by association, part X will have keywords A, B, C, which can be useful to retrieve it in a RAG context
    local table_file="$1"
    local parts_by_model_table="$2"

    local tmp_table="$(mktemp).tsv"
    # echo "Created temporary table: $tmp_table" >&2

    # concat all keywords but with duplicates 
    q -H -O -d $'\t' "
    SELECT 
        name, 
        description, 
        dimensions,
        GROUP_CONCAT(keywords, ', ') AS keywords
    FROM 
        $parts_by_model_table
    GROUP BY name, description, dimensions;
    " > "$tmp_table"

  python -c "
from collections import OrderedDict

# list of the most common stop words to ignore in the keywords
stop_words = set([
    'the', 'and', 'of', 'in', 'to', 'a', 'is', 'for', 'with', 'on', 'by',
    'as', 'that', 'this', 'it', 'from', 'are', 'at', 'be', 'or', 'an',
    'which', 'all', 'we', 'can', 'has', 'have', 'not', 'but', 'if',
    # add more stop words as needed
])

records = OrderedDict()
with open('$tmp_table') as f:
    next(f)
    for line in f:
        name, description, dimensions, keywords = line.strip().split('\t')
        if name not in records:
            records[name] = {
                'description': description,
                'dimensions': dimensions,
                'keywords': set()
            }
        for kws in keywords.split(','):
            sub_kws = kws.split()
            for skw in sub_kws:
                skw = skw.strip().lower()
                if skw and not skw.isnumeric() and skw not in stop_words:
                    records[name]['keywords'].add(skw)
print('name\tdescription\tdimensions\tkeywords')
for name, record in records.items():
    description, dimensions, keywords = record.values()
    print(f'''{name}\t{description}\t{dimensions}\t{', '.join(sorted(keywords))}''')
" > "$table_file"
}

part_chunk_tmpl="Name: %s
Description: %s
Dimensions: %s LDU
Keywords: %s
"

function chunk_models_parts() {
    local p_chunks_dir="$1"
    local m_chunks_dir="$2"

    tmp_dir="$(mktemp -d)"
    # echo "Created temporary directory: $tmp_dir" >&2

    cd "$tmp_dir" || exit 1

    # all models with their corresponding part infos and model keywords, in a tabular format
    parts_by_model_table "parts_by_model.tsv" "$m_chunks_dir" 

    # for every part of every model, get the part infos, aggregate all model keywords that use that part, 
    # and associate them to the part as single-word keywords
    parts_infos_kws_table "parts_infos_kws.tsv" "parts_by_model.tsv"
    
    cat parts_infos_kws.tsv \
        | tail +1 \
        | while IFS=$'\t' read -r p_name p_des p_dims p_kws; do
            echo "Processing part: $p_name" >&2
            chunk_content="$(printf "$part_chunk_tmpl" "$p_name" "$p_des" "$p_dims" "$p_kws")"
            echo "$chunk_content" > "$p_chunks_dir/${p_name}.chunks.md"
        done

    cd - >/dev/null || exit 1
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

# set -euo pipefail

# create output dirs if they don't exist
mkdir -p "$models_chunks_dir"
mkdir -p "$parts_chunks_dir"

prepare_rag_db="$(realpath "$prepare_rag_db")"
annotated_models_dir="$(realpath "$annotated_models_dir")"
models_chunks_dir="$(realpath "$models_chunks_dir")"
parts_chunks_dir="$(realpath "$parts_chunks_dir")"

chunk_models "$models_chunks_dir"

# parts_by_model_table "parts_by_model.tsv" "$models_chunks_dir"
# parts_with_kws_table "parts_with_kws.tsv" "parts_by_model.tsv"

chunk_models_parts "$parts_chunks_dir" "$models_chunks_dir"

### Parts chunks
# part_chunk_tmpl="Name: %s
# Description: %s
# Dimensions: %s LDU
# "

# sqlite-utils query "$prepare_rag_db" "select name, description, dim_x, dim_y, dim_z from VW_PART_INFOS_BBOXES ;" --tsv --no-headers \
#     | grep -v '^s\\' \
#     | tr -d '\r' \
#     | while IFS=$'\t' read -r p_name p_des dim_x dim_y dim_z; do
#         echo "Processing part: $p_name" >&2
#         dims="$(printf "%.01f x %.01f x %.01f" "$dim_x" "$dim_y" "$dim_z" | sed -E 's/\.0[ ]?/ /g')"
#         chunk_content="$(printf "$part_chunk_tmpl" "$p_name" "$p_des" "$dims")"
#         echo "$chunk_content" > "$parts_chunks_dir/${p_name}.chunks.md"
#     done


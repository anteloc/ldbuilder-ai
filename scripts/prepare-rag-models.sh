#!/bin/bash

source "$(dirname "$0")/common.sh"

data_dir="$(dirname "$0")/../data"

function usage() {
  echo "Usage: $(basename "$0") [--yes] [--step <step-num>] <models-dir> <output-dir>"
  echo "Selects and pre-processes LDraw models under models-dir (not parts!) for RAG use."
  echo "--step <step-num> (1 - $num_steps): start form a specific step, that will run the steps from that number onward. If not provided, all steps will be run."
  echo "--yes: automatically answer yes to all next-step prompts, effectively running all steps without stopping."
  echo "The output directories for the tmp files and the processed models will be created if they do not exist."
  echo "The preprocessed models will be saved under: output-dir/rag-models"
  echo "Example: $(basename "$0") /some/path/models-dir /some/path/output-dir"
}


step_counter=1

function next_step() {
    local step_desc="$1"
    local current_step="$step_counter"

    step_counter=$((step_counter + 1))

    if [ "$current_step" -lt "$from_step" ]; then
        echo "Skipping step $current_step: $step_desc"
        return 1
    fi

    echo
    echo "===================="
    echo "STEP: $current_step - $step_desc"
    echo "===================="
    echo

    [ -n "$always_yes" ] && return 0

    # Ask the user to continue, skip step or abort
    while true; do
        read -rp "Continue (Yes/Abort/Skip) [Y/a/s]: " answer
        answer="${answer:-Y}"
        case "$answer" in
            [Yy]* ) return 0;;
            [Aa]* ) echo "Aborting."; exit 0;;
            [Ss]* ) echo "Skipping step $current_step."; return 1;;
            * ) echo "Please answer Y (Yes), A (Abort), or S (Skip).";;
        esac
    done
}

function collect_model_sizes() {
    local models_dir="$1"
    local output_file="$2"

    # Will output: "MODEL_SIZES.tsv"
    tsv-models-by-size.sh "$models_dir"

    mv MODEL_SIZES.tsv "$output_file"
}

function select_models_by_quantiles() {
    local input_file="$1"
    local output_file="$2"
    local q_low="$3"
    local q_high="$4"

    local limits=$(python -c "
import pandas as pd

df = pd.read_csv('$input_file', sep='\t')
df['size_kb'] = pd.to_numeric(df['size_kb'], errors='coerce')
df = df.dropna(subset=['size_kb'])

q1 = df['size_kb'].quantile($q_low)
q3 = df['size_kb'].quantile($q_high)

print(f'{round(q1)},{round(q3)}')
")

    local min_size_kb=$(echo "$limits" | cut -d',' -f1)
    local max_size_kb=$(echo "$limits" | cut -d',' -f2)

    echo "Selected models size range: $min_size_kb KB to $max_size_kb KB"

    q -H -t "
    SELECT  
        '$models_dir/' || f.alias AS filepath, 
        f.size AS size
    FROM $input_file AS f
    WHERE f.size_kb >= $min_size_kb AND f.size_kb <= $max_size_kb;
    " > "$output_file"

    echo "Selected models by size count: $(wc -l < "$output_file")"
}

function select_models_with_steps() {
    local input_file="$1"
    local output_file="$2"

    # get the first column, filepaths list, and find models with at least one "0 STEP" line
    cut -d $'\t' -f1 "$input_file" \
        | tr '\n' '\0' \
        | xargs -0 rg -l '^0 STEP' \
        > "$output_file"

    echo "Selected models with steps count: $(wc -l < "$output_file")"
}

function select_models_without_lines() {
    local input_file="$1"
    local output_file="$2"
    local pattern="$3"

    # get the first column, filepaths list, and find models with no lines starting with the given pattern
    cut -d $'\t' -f1 "$input_file" \
        | tr '\n' '\0' \
        | xargs -0 rg --files-without-match "$pattern" \
        > "$output_file"

    echo "Selected models without lines count: $(wc -l < "$output_file")"
}

function copy_models_list_to_dir() {
    local input_file="$1"
    local output_file="$2"
    local output_dir="$3"

    # copy the files in the list to the output directory
    rsync -a --no-relative --files-from="$input_file" / "$output_dir/"

    ls -1 "$output_dir" | wc -l | awk '{print "Copied models count: " $1}'

}

function copy_valid_models_to_dir() {
    local input_file="$1"
    local output_dir="$2"

    tmp_valid_models_list="$(mktemp)"
    trap 'rm -f "$tmp_valid_models_list"' EXIT

    cat "$input_file" \
        | grep '"status": "OK"' \
        | jq -r '.model_file' \
        > "$tmp_valid_models_list"

    # copy the files in the list to the output directory
    rsync -a --no-relative --files-from="$tmp_valid_models_list" / "$output_dir/"

    ls -1 "$output_dir" | wc -l | awk '{print "Copied valid models count: " $1}'
}

function annotate_models_for_rag() {
    local input_dir="$1"
    local output_dir="$2"

    ldraw-annotate-models.py -d "$DB" -f "$input_dir" -o "$output_dir"

    cd $output_dir || exit 1

    for file in *.ann.mpd; do
        mv "$file" "${file%.ann.mpd}.mpd"
    done

    cd - > /dev/null || exit 1
}

function build_db() {
    local sel_models_dir="$1"
    local tmp_work_dir="$2"
    local db_file="$3"

    local ai_files_tsvs="$data_dir/tsv"

    touch "$db_file"
    db_file="$(realpath "$db_file")"

    sel_models_dir="$(realpath "$sel_models_dir")"

    cd "$tmp_work_dir" || exit 1

    cp "$ai_files_tsvs/COLORS.tsv" .
    cp "$ai_files_tsvs/MODEL_SIZES.tsv" .
    cp "$ai_files_tsvs/MODEL_NUM_PARTS.tsv" .
    cp "$ai_files_tsvs/MODEL_SUBMODELS.tsv" .
    cp "$ai_files_tsvs/MODEL_AI_CAT_DESC_KWS.tsv" .
    cp "$ai_files_tsvs/MODEL_AI_CATS_UNIQ.tsv" .
    cp "$ai_files_tsvs/MODEL_AI_KWS_UNIQ.tsv" .
    cp "$ai_files_tsvs/PART_BBOXES.tsv" .
    cp "$ai_files_tsvs/PART_CATEGORIES.tsv" .
    cp "$ai_files_tsvs/PART_INFOS.tsv" .
    cp "$ai_files_tsvs/PART_KEYWORDS.tsv" .

    # this will act as a join-filter for the queries
    tsv-models.sh "$sel_models_dir" # output: MODELS.tsv

    build-ldraw-db.sh "$db_file" .
}

### MAIN SCRIPT STARTS HERE

num_steps="$(cat $0 | grep -v 'function next_step' | grep -c 'next_step [0-9]\+')"

from_step=1
always_yes=""

first_arg="${1:-}"

if [[ "$first_arg" == "--step" ]]; then
  from_step="${2:-}"
  shift 2
elif [[ "$first_arg" == "--yes" ]]; then
  always_yes="yes"
  shift
fi

models_dir="$1"
output_dir="$2"

if [ -z "$models_dir" ] || [ -z "$output_dir" ]; then
  usage
  exit 1
fi

set -euo pipefail

DB="$data_dir/ldraw-info.db"

S01_OUT="01-MODEL_SIZES.tsv"
S02_OUT="02-SELECTED_BY_SIZE.tsv"
S03_OUT="03-SELECTED_WITH_STEPS.txt"
S04_OUT="04-SELECTED_0_1_ONLY.txt"
S05_OUT="05-COPIED_TO_TMP_MODELS.txt"
S06_OUT="06-VALIDATED_MODELS.jsonl"
RAG_DB="rag.db"

rag_models_dir="rag-models"
tmp_models_dir="tmp-models"
tmp_rag_models_dir="tmp-rag-models"
tmp_db_dir="tmp-rag-db"

# Create one or both dirs if they do not exist
mkdir -p "$output_dir/$rag_models_dir"
mkdir -p "$output_dir/$tmp_models_dir"
mkdir -p "$output_dir/$tmp_rag_models_dir"
mkdir -p "$output_dir/$tmp_db_dir"

output_dir="$(realpath "$output_dir")"

cd "$output_dir" || exit 1


### STEP
next_step "Collecting model sizes for models under dir: $models_dir" \
    && collect_model_sizes "$models_dir" "$S01_OUT"

### STEP
q_low="0.25"
q_high="0.90"

next_step "Selecting models between the $q_low and $q_high quantiles" \
    && select_models_by_quantiles "$S01_OUT" "$S02_OUT" "$q_low" "$q_high"

### STEP
# next_step "From the previous step, select models with at least one text line starting with: 0 STEP" \
#     && select_models_with_steps "$S02_OUT" "$S03_OUT"

### STEP
next_step "From the previous step, select files with no lines starting with: 2, 3, 4, or 5" \
    && select_models_without_lines "$S02_OUT" "$S04_OUT" "^[2345] "
# next_step "From the previous step, select files with no lines starting with: 2, 3, 4, or 5" \
#     && select_models_without_lines "$S03_OUT" "$S04_OUT" "^[2345] "

### STEP
next_step "Copy the selected models to the '$tmp_models_dir' directory" \
    && copy_models_list_to_dir "$S04_OUT" "$S05_OUT" "$tmp_models_dir"

### STEP
next_step "Validate models" && \
    ldraw-validator.py -d "$DB" -f "$tmp_models_dir" > "$S06_OUT" 2>/dev/null

### STEP
next_step "Copy valid models to the '$tmp_rag_models_dir' directory" && \
    copy_valid_models_to_dir "$S06_OUT" "$tmp_rag_models_dir"

### STEP
next_step "Sanitizing dos2unix contents" && \
    ldraw-sanitize.py --dos2unix "$tmp_rag_models_dir"
# next_step "Sanitizing filenames and dos2unix contents" && \
#     ldraw-sanitize.py --filepath "$tmp_rag_models_dir" && \
#     ldraw-sanitize.py --dos2unix "$tmp_rag_models_dir"

### STEP
next_step "Sanitizing coords and rots" && \
    ldraw-sanitize.py --coords "$tmp_rag_models_dir" && \
    ldraw-sanitize.py --rots "$tmp_rag_models_dir"

### STEP
next_step "Annotate models for RAG" && \
    annotate_models_for_rag "$tmp_rag_models_dir" "$rag_models_dir"
# next_step "Annotate models for RAG" && \
#     ldraw-annotate-models.py -d "$DB" -f "$tmp_rag_models_dir" -o "$rag_models_dir"

### STEP
next_step "Building database" && \
    build_db "$tmp_rag_models_dir" "$tmp_db_dir" "$RAG_DB"

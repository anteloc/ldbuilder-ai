#!/bin/bash
source "$(dirname "$0")/common.sh"

function describe_batch() {
    local batch_file="$1"
    local desc_batch="${batch_file}.desc.md"
    
    echo "[INFO] Processing batch file: $batch_file"
    
    while IFS= read -r model_path; do
        echo "[INFO] Processing: $model_path" 1>&2
        python $base_dir/src/python/ldraw_describe_model.py \
            -g $base_dir/specs/ldraw.lark \
            -d "$db" -m "$model_path" 2>> errors.log
    done < "$batch_file" > "$desc_batch"
}

output_basename_lib="MODELS_LIBRARY.md"
output_basename_idx="MODELS_INDEX.md"
batch_size=100

cwd_dir="$(pwd)"
cwd_dir="$(realpath "$cwd_dir")"

# e.g. models-index.jsonl file
db="$1"
models_dir="$2"

if [ -z "$db" ] || [ -z "$models_dir" ]; then
  echo "Usage: $(basename "$0") <models-index.jsonl>"
  echo "Builds a models library markdown file and a models index markdown file from it. 
  Outputs $output_basename_lib and $output_basename_idx files in the current directory."
  echo "Example: $(basename "$0") /some/path/models-index.jsonl"
  exit 1
fi

if [ ! -f "$db" ]; then
  echo "Error: File '$db' does not exist."
  exit 1
fi

if [ ! -d "$models_dir" ]; then
  echo "Error: Directory '$models_dir' does not exist."
  exit 1
fi

set -euo pipefail

models_dir="$(realpath "$models_dir")"
db="$(realpath "$db")"

tmp_dir="$(mktemp -d)"
# trap 'rm -rf "$tmp_dir"' EXIT

cd "$tmp_dir" || exit 1

echo "[INFO] Starting creating models library for models in: $models_dir"
echo "[INFO] Batch size: $batch_size"
echo "[INFO] Temporary directory created at: $tmp_dir"

touch errors.log

# python src/python/ldraw_describe_model.py -g specs/ldraw.lark -d ldraw.db -m ../ldraw-lib/models/42000-1.mpd
find "$models_dir" -type f -name "*.mpd" > models-list.txt

echo "[INFO] Total models found to process: $(wc -l < models-list.txt)"

# start date: yyyy-mm-dd hh:mm:ss
start_date=$(date +"%Y-%m-%d %H:%M:%S")

echo "[INFO] Process started at: $start_date"

# Split models-list.txt into models-batch-*.txt files with N lines each
# The smaller the batch size, the more parallel processes will be created
split -l "$batch_size" models-list.txt models-batch-

# Inform the user: number of batches created
num_batches=$(ls -1 models-batch-* | wc -l)
echo "[INFO] Processing num batches: $num_batches"

# On Ctrl+C, kill all background processes and exit
trap 'echo "Terminating..."; kill $(jobs -p); exit 1' SIGINT

# now, start a parallel download of all batches
for batch_file in models-batch-*; do
    describe_batch "$batch_file" &
done

wait

cat *.desc.md > "$output_basename_lib"

grep -n -A 5 '# LDraw Model:' "$output_basename_lib" \
        | awk -F ':' '/# LDraw Model/{print $0 " (line " $1 ")"; next} {print}' \
        | sed 's/..//' > "$output_basename_idx"

cp "$output_basename_lib" "$output_basename_idx" "$cwd_dir/"

end_date=$(date +"%Y-%m-%d %H:%M:%S")
echo "[INFO] Process ended at: $end_date"

echo "[INFO] Total duration: from $start_date to $end_date"

cd "$cwd_dir" || exit 1

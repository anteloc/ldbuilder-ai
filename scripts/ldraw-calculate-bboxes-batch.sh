#!/bin/bash

source "$(dirname "$0")/../include/env.inc.sh"

function usage() {
    echo "Usage: $(basename "$0") [--batch batch-size] [--db parts-database] [--ldraw-dir ldraw_directory] <--dir models_dir>"
    echo "--batch and --db are optional. If --batch is not specified, it will default to 1000. 
    If neither --db nor --ldraw-dir is specified, it will use the LDRAWDIR (LDRAW_DIR?) environment variable as the database directory."
    echo "Will calculate bounding boxes in JSON format for all .mpd, .dat and .ldr files in <models_dir> and its subdirectories."
    echo "If batch-size is not specified, it will default to 1000. The smaller the batch size, the more parallel processes will be created, which can speed up the processing but also increase CPU and memory usage."
    echo "The resulting JSON file will be saved next to the model file, with the same name but with -bbox.json extension."
    echo "For example, for a model file named <models_dir>/path/to/model/somefile.mpd, the resulting JSON file will be <models_dir>/path/to/model/somefile-bbox.json"
    echo "The resulting JSON file will be saved as <models_dir>/path/to/model/somebboxes.json"
    exit 1
}

function calculate_bbox_batch() {
    local batch_file="$1"
    echo "[INFO] Processing batch file: $batch_file"
    while IFS= read -r model_path; do
        local model_dir
        local model_file
        model_dir="$(dirname "$model_path")"
        model_file="$(basename "$model_path")"
        local bbox_file="${model_file%.*}-bbox.json"
        local bbox_path="$model_dir/$bbox_file"
        # echo "[INFO] Processing: $model_file"
        ldrlayout $db_arg --bbox "$model_path" > "$bbox_path" 2>> bbox-errors.log
    done < "$batch_file"

    local progress="$(fd --type f --glob '*-bbox.json' "$models_dir" | wc -l)"

    echo "[INFO] Progress: $progress files processed." 1>&2
}

cwd_dir="$(pwd)"
cwd_dir="$(realpath "$cwd_dir")"

# parse args
batch_size=1000
models_dir=""
db_arg=""

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --batch)
            batch_size="$2"
            shift 2
            ;;
        --dir)
            models_dir="$2"
            shift 2
            ;;
        --ldraw-dir)
            export LDRAWDIR="$2"
            export LDRAW_DIR="$LDRAWDIR"
            shift 2
            ;;
        --db)
            db_arg="--db $2"
            shift 2
            ;;
        *)
            echo "Unknown parameter passed: $1"
            usage
            ;;
    esac
done

[ -z "$models_dir" ]  &&  usage

# Verify directory exists
if [ ! -d "$models_dir" ]; then
    echo "Error: Directory '$models_dir' does not exist."
    exit 1
fi

models_dir="$(realpath "$models_dir")"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cd "$tmp_dir" || exit 1

echo "[INFO] Starting bounding box calculations for models in: $models_dir"
echo "[INFO] Using LDraw directory: $LDRAWDIR"
echo "[INFO] Batch size: $batch_size"
echo "[INFO] Temporary directory created at: $tmp_dir"

touch bbox-errors.log

# delete any existing *-bbox.json files in the models_dir to avoid confusion with old files, but only if the user confirms it, since it can be a destructive operation
existing=$(fd --type f --glob '*-bbox.json' "$models_dir" | wc -l)
echo "[INFO] Deleting existing $existing *-bbox.json files in $models_dir ..."

fd --type f --glob '*-bbox.json' "$models_dir" -x rm

# Find all .ldr, .dat and .mpd files in the specified directory and its subdirectories
find "$models_dir" -type f \( -iname "*.ldr" -o -iname "*.dat" -o -iname "*.mpd" \) > models-list.txt

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
    calculate_bbox_batch "$batch_file" &
done

wait

end_date=$(date +"%Y-%m-%d %H:%M:%S")
echo "[INFO] Process ended at: $end_date"

echo "[INFO] Total duration: from $start_date to $end_date"

cd "$cwd_dir" || exit 1

# Enable for debugging: Ask confirmation before deleting the temporary directory
# echo "Delete temporary directory '$tmp_dir' (Y/n)? "
# read -r response

# if [[ "$response" =~ ^[Yy]$ || -z "$response" ]]; then
#     rm -rf "$tmp_dir"
# fi
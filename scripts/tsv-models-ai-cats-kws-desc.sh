#!/bin/bash

source "$(dirname "$0")/../../include/env.inc.sh"

set -euo pipefail

source "$(dirname "$0")/common.sh"

output_basename_kw="MODEL_AI_CAT_DESC_KWS.tsv"
output_basename_cat_uniq="MODEL_AI_CATS_UNIQ.tsv"
output_basename_kw_uniq="MODEL_AI_KWS_UNIQ.tsv"

# e.g. models-index.jsonl file
models_idx="$1"

if [ -z "$models_idx" ]; then
  echo "Usage: $(basename "$0") <models-index.jsonl>"
  echo "Extracts the category, description, keywords and file name from the given models index previously created with a AI vision model from models screenshots, and creates $output_basename_kw, $output_basename_cat_uniq, and $output_basename_kw_uniq files in the current directory."
  echo "Example: $(basename "$0") /some/path/models-index.jsonl"
  exit 1
fi


# models index file must exist and be a file
if [ ! -f "$models_idx" ]; then
  echo "Error: $models_idx is not a file or does not exist."
  exit 1
fi

echo "Extracting metadata, please wait..."

tmp_dir=$(mktemp -d)
# trap 'rm -rf "$tmp_dir"' EXIT

echo "Created temporary directory: $tmp_dir"

models_idx="$(realpath "$models_idx")"

output_file_kw="$PWD/$output_basename_kw"
output_file_cat_uniq="$PWD/$output_basename_cat_uniq"
output_file_kw_uniq="$PWD/$output_basename_kw_uniq"

tmp_file_kw="$tmp_dir/${output_basename_kw%.tsv}.tmp"
tmp_file_cat_uniq="$tmp_dir/${output_basename_cat_uniq%.tsv}.tmp"
tmp_file_kw_uniq="$tmp_dir/${output_basename_kw_uniq%.tsv}.tmp"

models_idx_tmp="$tmp_dir/models-idx-tmp.jsonl"

cp "$models_idx" "$models_idx_tmp"

sed -i '' 's/.mpd.zip"/.mpd"/' "$models_idx_tmp"

# jsonl file format:
# {"category":"Technic","description":"A detailed model of a vehicle with a yellow and gray color scheme, featuring multiple axles and wheels.","keywords":["vehicle","model","axles","wheels","yellow"],"name":"9390-1_Race-Car.mpd.zip"}

printf "alias\tcategory\tdescription\tkeywords\n" > "$tmp_file_kw"
cat "$models_idx_tmp" \
    | jq -r '.name as $alias | .category as $cat | .description as $desc | .keywords as $kws | "\($alias)\t\($cat)\t\($desc)\t\($kws|join(", "))"' \
    >> "$tmp_file_kw"

printf "category\n" > "$tmp_file_cat_uniq"
cat "$models_idx_tmp" \
    | jq -r '.category' \
    | sort -u \
    >> "$tmp_file_cat_uniq"

printf "keyword\n" > "$tmp_file_kw_uniq"
cat "$models_idx_tmp" \
    | jq -r '.keywords[]' \
    | sort -u \
    >> "$tmp_file_kw_uniq"

mv "$tmp_file_kw" "$output_file_kw"
mv "$tmp_file_cat_uniq" "$output_file_cat_uniq"
mv "$tmp_file_kw_uniq" "$output_file_kw_uniq"

echo "Done! Output files: $(basename "$output_file_kw"), $(basename "$output_file_cat_uniq"), $(basename "$output_file_kw_uniq")"
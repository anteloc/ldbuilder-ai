#!/bin/bash

source "$(dirname "$0")/../../include/env.inc.sh"

set -euo pipefail

source "$(dirname "$0")/common.sh"

output_basename_kw="MODEL_KEYWORDS.tsv"
output_basename_cat="MODEL_CATEGORIES.tsv"
output_basename_th="MODEL_THEMES.tsv"

models_dir="$1"

if [ -z "$models_dir" ]; then
  echo "Usage: $(basename "$0") <models-dir>"
  echo "Extracts the !KEYWORDS, !CATEGORY, and !THEME meta keywords from the given models and creates $output_basename_kw, $output_basename_cat, and $output_basename_th files in the current directory."
  echo "Example: $(basename "$0") /some/path/prefix/models/models-dir"
  exit 1
fi


# models directory must exist and be a directory
if [ ! -d "$models_dir" ]; then
  echo "Error: $models_dir is not a directory or does not exist."
  exit 1
fi

echo "Extracting metadata, please wait..."

tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

echo "Created temporary directory: $tmp_dir"

models_dir="$(realpath "$models_dir")"

output_file_kw="$PWD/$output_basename_kw"
output_file_cat="$PWD/$output_basename_cat"
output_file_th="$PWD/$output_basename_th"

tmp_file_kw="$tmp_dir/${output_basename_kw%.tsv}.tmp"
tmp_file_cat="$tmp_dir/${output_basename_cat%.tsv}.tmp"
tmp_file_th="$tmp_dir/${output_basename_th%.tsv}.tmp"

extract_meta "!KEYWORDS" "$tmp_file_kw" "$models_dir"
extract_meta "!CATEGORY" "$tmp_file_cat" "$models_dir"
extract_meta "!THEME" "$tmp_file_th" "$models_dir"

# make parts agnostic from absolute paths
remove_path_prefix "$models_dir/" "$tmp_file_kw"
remove_path_prefix "$models_dir/" "$tmp_file_cat"
remove_path_prefix "$models_dir/" "$tmp_file_th"


q -O -t "select c1 as alias, group_concat(c2, ', ') as keywords from $tmp_file_kw group by c1" > "$tmp_dir/$output_basename_kw"
q -O -t "select c1 as alias, group_concat(c2, ', ') as categories from $tmp_file_cat group by c1" > "$tmp_dir/$output_basename_cat"
q -O -t "select c1 as alias, group_concat(c2, ', ') as themes from $tmp_file_th group by c1" > "$tmp_dir/$output_basename_th"

mv "$tmp_dir/$output_basename_kw" "$output_file_kw"
mv "$tmp_dir/$output_basename_cat" "$output_file_cat"
mv "$tmp_dir/$output_basename_th" "$output_file_th"

echo "Done! Output files: $(basename "$output_file_kw"), $(basename "$output_file_cat"), $(basename "$output_file_th")"
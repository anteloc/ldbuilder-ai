#!/bin/bash

source "$(dirname "$0")/../../include/env.inc.sh"
source "$(dirname "$0")/common.sh"

output_basename="MODEL_SUBMODELS.tsv"

models_dir="$1"

if [ -z "$models_dir" ]; then
  echo "Usage: $(basename "$0") <models-dir>"
  echo "Relationship table between models and their submodels for the models under the given directory, outputs a TSV in the current directory."
  echo "The output file will be named $output_basename and will have three columns: alias, num_submodels, and difficulty."
  echo "The alias is the filename with the models-dir path prefix removed."
  echo "Example: $(basename "$0") /some/path/prefix/models/models-dir"
  exit 1
fi

set -euo pipefail

tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

echo "Created temporary directory: $tmp_dir"

output_file="$PWD/$output_basename"

tmp_file="$tmp_dir/${output_basename%.tsv}.tmp"

printf "alias\tsubmodel\n" > "$tmp_file"

rg '^0[ \t]+FILE[ \t]' --type-add 'ldr:*.ldr' --type-add 'mpd:*.mpd' -tldr -tmpd "$models_dir" \
  | rg -v '//' \
  | sed -E 's/0[[:space:]]+FILE[[:space:]]+//' \
  | tr ':' '\t' \
  >> "$tmp_file"

remove_path_prefix "$models_dir/" "$tmp_file"

mv "$tmp_file" "$output_file"

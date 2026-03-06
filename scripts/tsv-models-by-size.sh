#!/bin/bash

source "$(dirname "$0")/../../include/env.inc.sh"
source "$(dirname "$0")/common.sh"

output_basename="MODEL_SIZES.tsv"

models_dir="$1"

if [ -z "$models_dir" ]; then
  echo "Usage: $(basename "$0") <models-dir>"
  echo "Collects the sizes for the models under the given directory on a TSV in the current directory."
  echo "The output file will be named $output_basename and will have three columns: alias, size (in bytes), and size in KB."
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

fd --type f -e 'mpd' -e 'ldr' '.' "$models_dir" -x stat -f $'%N\t%z' >> "$tmp_file"

remove_path_prefix "$models_dir/" "$tmp_file"

q -O -t "SELECT C1 AS alias, C2 AS size, CAST (ROUND(C2 / 1024.0) AS INTEGER) AS size_kb FROM $tmp_file" > "$output_file"
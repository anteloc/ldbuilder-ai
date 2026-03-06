#!/bin/bash

source "$(dirname "$0")/../../include/env.inc.sh"
source "$(dirname "$0")/common.sh"

output_basename="MODEL_NUM_PARTS.tsv"

models_dir="$1"

if [ -z "$models_dir" ]; then
  echo "Usage: $(basename "$0") <models-dir>"
  echo "Collects the approximate number of parts (pieces) for the models under the given directory on a TSV in the current directory."
  echo "The output file will be named $output_basename and will have three columns: alias, num_parts, and difficulty."
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

printf "alias\tnum_parts\n" > "$tmp_file"

rg -l -c '^1[ \t]+' --type-add 'ldr:*.ldr' --type-add 'mpd:*.mpd' -tldr -tmpd "$models_dir" | tr ':' '\t' >> "$tmp_file"

remove_path_prefix "$models_dir/" "$tmp_file"

q_low="0.25"
q_high="0.75"

limits=$(quantiles_from_file "$tmp_file" "num_parts" "$q_low" "$q_high")

min_size=$(echo "$limits" | cut -d',' -f1)
max_size=$(echo "$limits" | cut -d',' -f2)

echo "Selected models num_parts range: $min_size to $max_size"

q -H -O -t "SELECT 
          alias, 
          num_parts,
          (
            case 
              when num_parts < $min_size then 'simple' 
              when num_parts > $max_size then 'complex' 
              else 'medium' 
            end
            ) AS difficulty
        FROM $tmp_file" > "$output_file"
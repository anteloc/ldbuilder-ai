#!/bin/bash

# This is actually a thin wrapper around ldraw-model-name-description.py, in order to have 
# a consistent naming for all the tsv-extracting .sh scripts

source "$(dirname "$0")/../../include/env.inc.sh"

output_file="PART_INFOS.tsv"

ldraw_dir="$1"

if [ -z "$ldraw_dir" ]; then
  echo "Usage: $(basename "$0") <ldraw-dir>"
  echo "Extracts the alias, name, description from the parts under the given LDraw directory and creates $output_file file in the current directory."
  echo "Example: $(basename "$0") /some/path/prefix/ldraw-lib/ldraw"
  exit 1
fi

# parts directory must exist and be a directory
if [ ! -d "$ldraw_dir" ]; then
  echo "Error: $ldraw_dir is not a directory or does not exist."
  exit 1
fi


ldraw-model-name-description.py -f "$ldraw_dir" -p "$ldraw_dir/parts/" -p "$ldraw_dir/p/" -p "$ldraw_dir/" -t "$output_file"

echo "Output written to: $output_file"


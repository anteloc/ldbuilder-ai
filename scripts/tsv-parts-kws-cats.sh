#!/bin/bash

set -euo pipefail

source "$(dirname "$0")/../../include/env.inc.sh"
source "$(dirname "$0")/common.sh"


output_basename_kw="PART_KEYWORDS.tsv"
output_basename_cat="PART_CATEGORIES.tsv"
output_basename_rebrick="PARTS_REBRICKABLE_CAT.tsv"
output_basename_bricklink="PARTS_BRICKLINK_CAT.tsv"

ldraw_dir="$1"

if [ -z "$ldraw_dir" ]; then
  echo "Usage: $(basename "$0") <ldraw-dir>"
  echo "Extracts the !KEYWORDS, !CATEGORY meta keywords from the LDraw parts and creates $output_basename_kw, $output_basename_cat, $output_basename_rebrick and $output_basename_bricklink files in the current directory."
  echo "Example: $(basename "$0") /some/path/prefix/ldraw-lib/ldraw"
  exit 1
fi


# parts directory must exist and be a directory
if [ ! -d "$ldraw_dir" ]; then
  echo "Error: $ldraw_dir is not a directory or does not exist."
  exit 1
fi

echo "Extracting metadata, please wait..."

tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

echo "Created temporary directory: $tmp_dir"

ldraw_dir="$(realpath "$ldraw_dir")"
output_file_kw="$PWD/$output_basename_kw"
output_file_cat="$PWD/$output_basename_cat"
output_file_rebrick="$PWD/$output_basename_rebrick"
output_file_bricklink="$PWD/$output_basename_bricklink"
tmp_file_kw="$tmp_dir/${output_basename_kw%.tsv}.tmp"
tmp_file_cat="$tmp_dir/${output_basename_cat%.tsv}.tmp"
tmp_file_rebrick="$tmp_dir/${output_basename_rebrick%.tsv}.tmp"
tmp_file_bricklink="$tmp_dir/${output_basename_bricklink%.tsv}.tmp"

extract_meta "!KEYWORDS" "$tmp_file_kw" "$ldraw_dir"
extract_meta "!CATEGORY" "$tmp_file_cat" "$ldraw_dir"

# make parts agnostic from absolute paths
remove_path_prefix "$ldraw_dir/parts/" "$tmp_file_kw"
remove_path_prefix "$ldraw_dir/p/" "$tmp_file_kw"
remove_path_prefix "$ldraw_dir/" "$tmp_file_kw"

remove_path_prefix "$ldraw_dir/parts/" "$tmp_file_cat"
remove_path_prefix "$ldraw_dir/p/" "$tmp_file_cat"
remove_path_prefix "$ldraw_dir/" "$tmp_file_cat"


q -O -t "select c1 as alias, group_concat(c2, ', ') as keywords from $tmp_file_kw group by c1" > "$tmp_dir/$output_basename_kw"
q -O -t "select c1 as alias, group_concat(c2, ', ') as categories from $tmp_file_cat group by c1" > "$tmp_dir/$output_basename_cat"

# Rebrickable parts equivalence, as a column
q -H -O -t "select alias, keywords from $tmp_dir/$output_basename_kw where upper(keywords) like '%REBRICKABLE%'" >> "$tmp_dir/rebrickable-kws.tsv"
# Bricklink parts equivalence, as a column
q -H -O -t "select alias, keywords from $tmp_dir/$output_basename_kw where upper(keywords) like '%BRICKLINK%'" >> "$tmp_dir/bricklink-kws.tsv"

echo "catalog_part_num" > "$tmp_dir/parts-rebrickable.col"
cat "$tmp_dir/rebrickable-kws.tsv" | cut -d $'\t' -f2 | rg -oP 'Rebrickable\s+\K[^,]+' >> "$tmp_dir/parts-rebrickable.col"

paste <(q -H -O -t "select alias from $tmp_dir/rebrickable-kws.tsv") <(cat "$tmp_dir/parts-rebrickable.col") > "$tmp_file_rebrick"

echo "catalog_part_num" > "$tmp_dir/parts-bricklink.col"
cat "$tmp_dir/bricklink-kws.tsv" | cut -d $'\t' -f2 | rg -ioP 'Bricklink\s+\K[^,]+' >> "$tmp_dir/parts-bricklink.col"

paste <(q -H -O -t "select alias from $tmp_dir/bricklink-kws.tsv") <(cat "$tmp_dir/parts-bricklink.col") > "$tmp_file_bricklink"

mv "$tmp_dir/$output_basename_kw" "$output_file_kw"
mv "$tmp_dir/$output_basename_cat" "$output_file_cat"
mv "$tmp_file_rebrick" "$output_file_rebrick"
mv "$tmp_file_bricklink" "$output_file_bricklink"

echo "Done! Output files: $(basename "$output_file_kw"), $(basename "$output_file_cat"), $(basename "$output_file_rebrick"), $(basename "$output_file_bricklink")"


#!/bin/bash

source "$(dirname "$0")/../../include/env.inc.sh"

set -euo pipefail

output_basename="PART_BBOXES.tsv"

ldraw_dir="$1"

if [ -z "$ldraw_dir" ]; then
  echo "Usage: $(basename "$0") <ldraw-dir>"
  echo "Calculates all the bounding boxes for the given ldraw directory, not only the actual parts, and creates a $output_basename file in the current directory."
  echo "Calculating all bounding boxes is required due to some parts, subparts, etc. depending on the bounding boxes of other parts, so to have a complete and correct set of bounding boxes we need to calculate them for all the files in the given ldraw directory."
  echo "Example: $(basename "$0") /some/path/prefix/ldraw-lib/ldraw"
  echo "NOTE: the last part of the path should always be 'ldraw'"
  exit 1
fi

# parts directory must exist and be a directory
if [ ! -d "$ldraw_dir" ]; then
  echo "Error: $ldraw_dir is not a directory or does not exist."
  exit 1
fi

tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

echo "Created temporary directory: $tmp_dir"

ldraw_dir="$(realpath "$ldraw_dir")"
output_file="$PWD/$output_basename"

echo "Starting bounding box calculations, this will take a while, please wait..."

# Batch size=1000 for the usual size of the parts directory yields good performance
ldraw-calculate-bboxes-batch.sh --batch 1000 --dir "$ldraw_dir" --ldraw-dir "$ldraw_dir"

echo "Calculations done, now processing results and creating TSV file..."

fd --type f --glob '*-bbox.json' "$ldraw_dir" -x cat > "$tmp_dir/part-bboxes.json"

cd "$tmp_dir" || exit 1

cat "part-bboxes.json" | grep -v -i 'Skipping' | jq -c '.' > "part-bboxes-totals.json"
cat "part-bboxes-totals.json" | grep '"status":"error"' > "part-bboxes-errors.json"
cat "part-bboxes-totals.json" | grep -v '"status":"error"' > "part-bboxes-clean.json"

skipped="$(grep -i -c 'Skipping' part-bboxes.json)"
total_processed="$(wc -l < part-bboxes-totals.json)"
with_errors="$(wc -l < part-bboxes-errors.json)"
without_errors="$(wc -l < part-bboxes-clean.json)"

echo "STATS:"
echo "Total files processed: $total_processed"
echo "Total files skipped (not processed): $skipped"
echo "Files with errors: $with_errors"
echo "Files without errors: $without_errors"
echo "Skipped rate: $(awk "BEGIN {printf \"%.4f\", ($skipped / ($total_processed + $skipped)) * 100}")%"
echo "Error rate: $(awk "BEGIN {printf \"%.2f\", ($with_errors / $total_processed) * 100}")%"

cat part-bboxes-clean.json | jq -c '{
  alias: .file,
 min_x: .bounding_box.min.x,
 min_y: .bounding_box.min.y,
 min_z: .bounding_box.min.z,
 max_x: .bounding_box.max.x,
 max_y: .bounding_box.max.y,
 max_z: .bounding_box.max.z,
 center_x: .bounding_box.center.x,
 center_y: .bounding_box.center.y,
 center_z: .bounding_box.center.z,
 dim_x: .bounding_box.dimensions.x,
 dim_y: .bounding_box.dimensions.y,
 dim_z: .bounding_box.dimensions.z,
 diag: .bounding_box.dimensions.diagonal,
 complete: .bounding_box.complete
 }' | sed -e "s|$ldraw_dir/||" -e 's#p/##; s#parts/##' | sort | uniq > part-bboxes-tsv.json

printf "alias\tmin_x\tmin_y\tmin_z\tmax_x\tmax_y\tmax_z\tcenter_x\tcenter_y\tcenter_z\tdim_x\tdim_y\tdim_z\tdiag\tcomplete\n" > "$tmp_dir/$output_basename"
cat part-bboxes-tsv.json | jq -r -c '[.alias, .min_x, .min_y, .min_z, .max_x, .max_y, .max_z, .center_x, .center_y, .center_z, .dim_x, .dim_y, .dim_z, .diag, .complete] | @tsv' >> "$tmp_dir/$output_basename"

echo "TSV file created: $tmp_dir/$output_basename, $(wc -l < "$tmp_dir/$output_basename") lines (including header)"

mv "$tmp_dir/$output_basename" "$output_file"

echo "Done! Output file: $output_file"

# ask if delete the *-bbox.json files, due to the fact that it took a long time to calculate them, so maybe the user wants to keep them for later analysis or debugging
echo "Do you want to delete the intermediate *-bbox.json files? (y/n) "
read -r response 
if [[ "$response" =~ ^[Yy]$ ]]; then
  fd --type f --glob '*-bbox.json' "$ldraw_dir" -x rm
  echo "Intermediate *-bbox.json files deleted."
else
  echo "Intermediate *-bbox.json files kept."
fi
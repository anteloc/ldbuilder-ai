#!/bin/bash

set -euo pipefail

source "$(dirname "$0")/../../include/env.inc.sh"

db_schema_ddl="$(dirname "$0")/build-ldraw-db.sql"

dest_db="$1"
tsv_dir="$2"

if [ -z "$dest_db" ] || [ -z "$tsv_dir" ]; then
  echo "Usage: $(basename "$0") <destination-db-file> <tsv-directory>"
  echo "Builds an SQLite database for the LDraw parts library and models, using the TSV and other sources available in the specified TSV directory."
  echo "The resulting database file will be created at the specified path, creating parent directories if they do not exist."
  echo "Note: the TSV files must be in the expected format and have the expected names as defined in the build-ldraw-db.sql schema file."
  echo "Example: $(basename "$0") /some/path/ldraw.db /path/to/tsv/files/"
  exit 1
fi

if [ ! -d "$tsv_dir" ]; then
  echo "Error: $tsv_dir is not a directory or does not exist."
  exit 1
fi

tsv_dir="$(realpath "$tsv_dir")"

# ask for confirmation in case the destination db file already exists, since it will be overwritten
if [ -f "$dest_db" ]; then
  read -p "The file '$dest_db' already exists. Do you want to overwrite it? (y/N) " confirm
  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborting."
    exit 1
  fi
fi

[ -f "$dest_db" ] && echo "Removing old DB: $dest_db" && rm "$dest_db"

mkdir -p "$(dirname "$dest_db")"
sqlite3 "$dest_db" < "$db_schema_ddl"

dest_db="$(realpath "$dest_db")"


# these should have an equivalent in the DB build-ldra-db.sql file
# TODO maybe the non-AI model categories, keywords, themes are not needed, since data extracted directly from the models text is sometimes incomplete
tsv_files=$(cat <<EOF
COLORS.tsv
MODEL_AI_CAT_DESC_KWS.tsv
MODEL_AI_CATS_UNIQ.tsv
MODEL_AI_KWS_UNIQ.tsv
MODEL_NUM_PARTS.tsv
MODEL_SUBMODELS.tsv
MODEL_SIZES.tsv
PART_BBOXES.tsv
PART_CATEGORIES.tsv
PART_INFOS.tsv
PART_KEYWORDS.tsv
MODELS.tsv
EOF
)

# tsv_files=$(cat <<EOF
# CATEGORIES.tsv
# COLORS.tsv
# MODEL_AI_CAT_DESC_KWS.tsv
# MODEL_NUM_PARTS.tsv
# MODEL_CATEGORIES.tsv
# MODEL_KEYWORDS.tsv
# MODEL_SIZES.tsv
# MODEL_THEMES.tsv
# PART_BBOXES.tsv
# PART_CATEGORIES.tsv
# PART_INFOS.tsv
# PART_KEYWORDS.tsv
# EOF
# )

# issues with PARTS_REBRICKABLE_CAT.tsv, PARTS_BRICKLINK_CAT.tsv not UNIQUE aliases, so skipping for now

for t in $(echo "$tsv_files"); do 
    tbl_name=$(echo "$t" | cut -d. -f1)
    tsv_path="$tsv_dir/$t"
    if [ -f "$tsv_path" ]; then
        echo "Importing $t into table $tbl_name..."
        sqlite-utils insert "$dest_db" "$tbl_name" "$tsv_path" --tsv
    else
        echo "Warning: $tsv_path not found, skipping..."
    fi
done

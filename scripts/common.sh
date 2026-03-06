#!/bin/bash

function extract_meta() {
    local meta_name="$1"
    local dest_file="$2"
    local models_dir="$3"
    rg "0 $meta_name " $models_dir | sort | uniq | sed "s|:0 $meta_name|\t|" > "$dest_file"
}

function remove_path_prefix() {
    local prefix="$1"
    local file="$2"
    sed -i.bak "s|^$prefix||" "$file"
}

function quantiles_from_file() {
    local input_file="$1"
    local col_name="$2"
    local q_low="$3"
    local q_high="$4"

    # calculate quantiles for the given column using pandas, and select models within that range
    local limits=$(python -c "
import pandas as pd

df = pd.read_csv('$input_file', sep='\t')
df['$col_name'] = pd.to_numeric(df['$col_name'], errors='coerce')
df = df.dropna(subset=['$col_name'])

q1 = df['$col_name'].quantile($q_low)
q3 = df['$col_name'].quantile($q_high)

print(f'{round(q1)},{round(q3)}')
")

    echo "$limits"
}

function select_models_by_quantiles_col() {
    local input_file="$1"
    local col_name="$2"
    local q_low="$3"
    local q_high="$4"

    # calculate quantiles for the given column using pandas, and select models within that range
    local limits=$(quantiles_from_file "$input_file" "$col_name" "$q_low" "$q_high")

    local min_size=$(echo "$limits" | cut -d',' -f1)
    local max_size=$(echo "$limits" | cut -d',' -f2)

    echo "Selected models size range: $min_size to $max_size"

    q -H -t "
    SELECT  
        *
    FROM $input_file AS f
    WHERE f.$col_name >= $min_size AND f.$col_name <= $max_size;
    "
}
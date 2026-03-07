#!/bin/bash
raw_base='https://raw.githubusercontent.com/anteloc/ldbuilder-ai/master/results'
base_dir="$(dirname $0)"
base_dir="$(realpath $base_dir)"
ldraw_dir="$base_dir/../../ldraw-lib/ldraw"
ldraw_dir="$(realpath $ldraw_dir)"

while IFS= read -r line; do
    name="$(echo "$line" | jq -r '.name')"
    subdir="$(dirname "$name")"
    filename="$(basename "$name")"
    file_base="${filename%.*}" # remove file extension for thumbnail and links
    description="$(echo "$line" | jq -r '.description')"

    # find the file by name, just in case a .glb is referenced in the index instead of the original model
    model_filename=""

    if [[ -f "models/$subdir/${file_base}.mpd" ]]; then
        model_filename="${file_base}.mpd"
    elif [[ -f "models/$subdir/${file_base}.ldr" ]]; then
        model_filename="${file_base}.ldr"
    fi

    echo "Processing model: $model_filename" 1>&2

    # generate .glb for the viewer
    mpd2glb.sh -c meshopt -l $ldraw_dir -o "models/$subdir/${file_base}.glb" "models/$subdir/$model_filename" 1>&2

    # generate thumbnail
    mkdir -p "thumbnails/$subdir"
    mkdir -p "thumbnails-small/$subdir"

    # render all the other perspectives, to get a full set of thumbnails for the viewer
    for view in isometric front back left right top bottom; do
        # no suffix for isometric view, it will be used together with the model, so only extension changes
        if [[ "$view" == "isometric" ]]; then
            thumb_file="${file_base}.png"
        else
            thumb_file="${file_base}-${view}.png"
        fi

        ldr2img --view "$view" --ldraw-dir "$ldraw_dir" -o "thumbnails/$subdir/$thumb_file" "models/$subdir/$model_filename" 1>&2
        magick "thumbnails/$subdir/$thumb_file" -resize 50% "thumbnails-small/$subdir/$thumb_file"
    done

    # Output markdown for this model
    src_link="${raw_base}/models/$subdir/$model_filename"
    thumb_link="${raw_base}/thumbnails-small/$subdir/$thumb_file"

    printf '### **Prompt:** _%s_\n\n' "$description"
    printf '| [%s](%s) |\n' "$model_filename" "$src_link"
    printf '|:--:|\n'
    printf '| ![%s](%s) |\n\n' "$description" "$thumb_link"

done < models-index.jsonl > results.md


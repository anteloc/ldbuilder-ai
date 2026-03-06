#!/bin/bash
raw_base='https://raw.githubusercontent.com/anteloc/ldbuilder-ai/master/results'
base_dir="$(dirname $0)"
base_dir="$(realpath $base_dir)"
ldraw_dir="$base_dir/../../ldraw-lib/ldraw"

while IFS= read -r line; do
    name="$(echo "$line" | jq -r '.name')"
    name="${name%.*}" # remove file extension for thumbnail and links
    description="$(echo "$line" | jq -r '.description')"

    # find the file by name, just in case a .glb is referenced in the index instead of the original model
    model_file=""

    if [[ -f "models/${name}.mpd" ]]; then
        model_file="${name}.mpd"
    elif [[ -f "models/${name}.ldr" ]]; then
        model_file="${name}.ldr"
    fi

    echo "Processing model: $model_file" 1>&2

    # generate .glb for the viewer
    mpd2glb.sh -c meshopt -l $ldraw_dir $model_file "${name}.glb"


    # generate thumbnail
    thumb_file="${name}.png"
    thumbs_file_dir="$(dirname $thumb_file)"

    mkdir -p "thumbnails/$thumbs_file_dir"
    mkdir -p "thumbnails-small/$thumbs_file_dir"

    # render all the other perspectives, to get a full set of thumbnails for the viewer
    for view in isometric front back left right top bottom; do

        # no suffix for isometric view, it will be used together with the model, so only ext changes
        if [[ "$view" == "isometric" ]]; then
            thumb_file="${name}.png"
        else
            thumb_file="${name}-${view}.png"
        fi

        ldr2img --view "$view" --ldraw-dir "$ldraw_dir" -o "thumbnails/$thumb_file" "models/${model_file}" 1>&2
        magick "thumbnails/$thumb_file" -resize 50% "thumbnails-small/$thumb_file"
    done

    # Output markdown for this model
    src_link="${raw_base}/models/${model_file}"
    thumb_link="${raw_base}/thumbnails-small/${thumb_file}"

    printf '### **Prompt:** _%s_\n\n' "$description"
    printf '| [%s](%s) |\n' "$model_file" "$src_link"
    printf '|:--:|\n'
    printf '| ![%s](%s) |\n\n' "$description" "$thumb_link"

done < models-index.jsonl > results.md

# Create reduced-size thumbnails for including in other documents
echo "Creating reduced size thumbnails..." 1>&2

[ -d "thumbnails-small" ] && rm -r "thumbnails-small"
mkdir "thumbnails-small"

cp -r thumbnails/* "thumbnails-small/"

find "thumbnails-small" -type f -name "*.png" -exec magick {} -resize 50% {} \;


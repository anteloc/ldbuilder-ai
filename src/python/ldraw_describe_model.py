#!/usr/bin/env python3
import os
import sys
from collections import defaultdict

import click
# import pandas as pd
import sqlite3

from ldraw_parser import parse_model_semantic
from functools import lru_cache


# ---------------------------------------------------------------------------
# Mode-variant phrases
# ---------------------------------------------------------------------------

_PHRASES = {
    "instructions": {
        "intention":       "We are going to describe how to build this model step by step.",
        "verb":            "build",
        "piece_intro":     "Let's describe",
        "placement":       "To place it correctly,",
        "position_prefix": "Move the piece",
        "finish":          "Model finished! You have now a step-by-step description of how to build this model!",
    },
    "layout": {
        "intention":       "We are going to describe how this model looks like.",
        "verb":            "describe",
        "piece_intro":     "Describing layout for",
        "placement":       "Its placement is as follows:",
        "position_prefix": "The piece is located at: {xyz}",
        "finish":          "This is the current layout. You now have a description of how this model looks like!",
    },
}


# ---------------------------------------------------------------------------
# Structural output templates
# ---------------------------------------------------------------------------

_TMPL_MODEL_HEADER = """
# LDraw Model: '{model_name}'

{intention}

## Model source code

```ldraw
{model_contents}
```

"""

_TMPL_SUBMODEL_HEADER = """## Submodel #{submodel_num}: '{submodel_name}'

Now, we are going to {verb} a model named '{submodel_name}'. It's a '{submodel_desc}'.

### Pieces to place:
"""

_TMPL_PIECE = """
{piece_intro} 'Piece #{piece_idx}' for this submodel. It's part name is '{part_name}', a '{part_desc}', in color '{desc_color}'.
{placement}

    First:
    {desc_rotation}
    And then:
    {desc_position}
    """

_TMPL_OVERALL = """
## Overall Model Description:

Now, let's summarize the overall model pieces placement, back-to-front and left-to-right:

{overall_description}
"""


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

# LDraw coordinate axes: x left-to-right, y bottom-to-top (inverted), z back-to-front (inverted)
_COORD_IDX  = {'x': 0, 'y': 1, 'z': 2}
_COORD_SIGN = {'x': 1, 'y': -1, 'z': -1}  # flips sort direction to match spatial "ascending"


def _coord_sort_key(axis: str):
    idx, sign = _COORD_IDX[axis], _COORD_SIGN[axis]
    return lambda p: sign * p['position'][idx]


def filter_submodels(sem_model: dict) -> list:
    if sem_model["type"] == "mpd":
        return [item for subfile in sem_model["model"] for item in subfile["subfile"]]
    if sem_model["type"] == "plain":
        return sem_model["model"]
    return []


def find_color_name(color_code: str, color_table_df) -> str:
    row = color_table_df[color_table_df["CODE"] == color_code]
    if not row.empty:
        return row.iloc[0]["COLOUR"]
    row = color_table_df[color_table_df["VALUE"] == color_code.upper()]
    return row.iloc[0]["COLOUR"] if not row.empty else f"code {color_code}"


def group_pieces_by_coordinate(pieces: list, axis: str) -> dict:
    idx = _COORD_IDX[axis]
    groups: dict = defaultdict(list)
    for p in pieces:
        groups[p['position'][idx]].append(p)
    return dict(groups)


def sort_groups_by_coordinate(groups: dict, axis: str, order: str) -> list:
    sign = _COORD_SIGN[axis]
    return [groups[k] for k in sorted(groups, key=lambda k: sign * k, reverse=(order == 'desc'))]


def sort_pieces_by_coordinate(pieces: list, axis: str, order: str) -> list:
    return sorted(pieces, key=_coord_sort_key(axis), reverse=(order == 'desc'))

# ---------------------------------------------------------------------------
# Database access helpers
# ---------------------------------------------------------------------------
def configure_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.row_factory = sqlite3.Row

COLORS_TABLE: dict[str, str] = {}

@lru_cache(maxsize=200_000)
def load_colors_table(conn: sqlite3.Connection) -> None:
    global COLORS_TABLE
    cur = conn.execute("SELECT code, color FROM COLORS")
    # get row fields by name, and build a dict of code to name
    COLORS_TABLE = {row['code']: row['color'] for row in cur.fetchall()}
    cur.close()

@lru_cache(maxsize=200_000)
def part_info_bbox(conn: sqlite3.Connection, alias: str) -> tuple[dict[str, str], dict[str, str | float]]:
    """
    Returns the part info for the given alias, including the name and description from the database, or "missing" if not available.
    """

    # test several combinations: depending on the source of the alias, it could be Windows-style, Unix-style, escaped backslashes, etc.
    unix_alias = alias.replace("\\", "/") # in some instances, this will generate unix_alias_1="48//some_part.dat"
    sanitized_alias = unix_alias.replace("//", "/") # this we will take as reference: the sanitize

    win_alias_1 = alias.replace("/", "\\")
    win_alias_2 = alias.replace("/", "\\\\")

    cur = conn.execute(f"""
                                SELECT '{sanitized_alias}' as alias, name, description
                                FROM PART_INFOS PI 
                                WHERE UPPER(PI.alias) IN (UPPER(?), UPPER(?), UPPER(?), UPPER(?))
                            """, (unix_alias, sanitized_alias, win_alias_1, win_alias_2))
    p_info = cur.fetchone()
    cur.close()

    cur = conn.execute("""
                                SELECT *
                                FROM PART_BBOXES
                                WHERE alias = ?
                            """, (sanitized_alias,))
    
    p_bbox = cur.fetchone()
    cur.close()

    p_info = p_info if p_info else {}
    p_bbox = p_bbox if p_bbox else {}

    return dict(p_info), dict(p_bbox)

# ---------------------------------------------------------------------------
# Rotation description
# ---------------------------------------------------------------------------

def rotation_layout(yaw: float, pitch: float, roll: float) -> str:
    yaw_part   = f"The piece is rotated {yaw:.2f}° around its vertical axis," if abs(yaw) > 1e-9 else "The piece is not rotated around its vertical axis,"
    pitch_part = f"and rotated {pitch:.2f}° around its side-to-side horizontal axis," if abs(pitch) > 1e-9 else "and not rotated around its side-to-side horizontal axis,"
    roll_part  = f"and rotated {roll:.2f}° around its front-to-back horizontal axis." if abs(roll) > 1e-9 else "and not rotated around its front-to-back horizontal axis."
    return f"\n{yaw_part}\n{pitch_part}\n{roll_part}\n"


def rotation_instructions(yaw: float, pitch: float, roll: float) -> str:
    yaw_part   = f"Rotate the piece {yaw:.2f}° around its vertical axis," if abs(yaw) > 1e-9 else "Don't rotate the piece around its vertical axis,"
    pitch_part = f"rotate {pitch:.2f}° around its side-to-side horizontal axis," if abs(pitch) > 1e-9 else "don't rotate the piece around its side-to-side horizontal axis,"
    roll_part  = f"and {roll:.2f}° around its front-to-back horizontal axis." if abs(roll) > 1e-9 else "and don't rotate the piece around its front-to-back horizontal axis."
    return f"\n{yaw_part}\n{pitch_part}\n{roll_part}\n"


def describe_rotation(ypr: tuple, mode: str) -> str:
    yaw, pitch, roll = ypr
    # LDraw sign conventions derived from empirical testing
    ldraw_yaw, ldraw_pitch, ldraw_roll = -yaw, pitch, -roll
    if mode == "layout":
        return rotation_layout(ldraw_yaw, ldraw_pitch, ldraw_roll)
    return rotation_instructions(ldraw_yaw, ldraw_pitch, ldraw_roll)


# ---------------------------------------------------------------------------
# Piece and group description
# ---------------------------------------------------------------------------

def describe_position(xyz: tuple, mode: str) -> str:
    x, y, z = xyz
    ldraw_x, ldraw_y, ldraw_z = -x, -y, -z

    def lr(val: float) -> str:
        if val > 0:
            return f"{abs(val):.2f} units left"
        if val < 0:
            return f"{abs(val):.2f} units right"
        return "no left/right movement"

    def fb(val: float) -> str:
        if val > 0:
            return f"{abs(val):.2f} units forward"
        if val < 0:
            return f"{abs(val):.2f} units back"
        return "no forward/backward movement"

    def ud(val: float) -> str:
        if val > 0:
            return f"{abs(val):.2f} units up"
        if val < 0:
            return f"{abs(val):.2f} units down"
        return "no up/down movement"

    parts  = ", ".join([ud(ldraw_y), lr(ldraw_x), fb(ldraw_z)])
    prefix = _PHRASES[mode]["position_prefix"].format(xyz=xyz)
    return f"\n{prefix}, {parts}.\n"


def describe_group_position(sorted_lr_group: list) -> str:
    first = sorted_lr_group[0]
    lines = [
        f"At the leftmost position, 'Piece #{first['piece_idx']}', part name '{first['part_name']}', a '{first['part_desc']}', in color '{first['desc_color']}'."
    ]
    lines += [
        f"To the right of it, we have 'Piece #{p['piece_idx']}', part name is '{p['part_name']}', a '{p['part_desc']}', in color '{p['desc_color']}'."
        for p in sorted_lr_group[1:]
    ]
    return "\n".join(lines)

def describe_grouped_pieces(all_pieces: list) -> str:
    grouped_bf  = group_pieces_by_coordinate(all_pieces, "z")
    bf_groups   = sort_groups_by_coordinate(grouped_bf, "z", "asc")
    lr_groups   = [sort_pieces_by_coordinate(g, "x", "asc") for g in bf_groups]
    group_descs = [describe_group_position(g) for g in lr_groups]

    sections  = [f"At the backmost position, we have the following group of pieces:\n{group_descs[0]}"]
    sections += [f"In front of the previous group, we have the following group:\n{d}" for d in group_descs[1:]]
    return "\n\n".join(sections)


def describe_part_ref(conn: sqlite3.Connection, part_ref: dict, mode: str) -> str:
    piece_idx = part_ref["piece_idx"]
    file_ref  = part_ref["file_ref"]

    # part_row = bom_df[bom_df["filename"] == os.path.basename(file_ref)]
    p_info, p_bbox = part_info_bbox(conn, file_ref)

    if p_info:
        part_name = p_info["name"]
        part_desc = p_info["description"]
    else:
        part_name = file_ref
        part_desc = "(description?)"

    desc_color = COLORS_TABLE.get(part_ref["color"], f"Color{part_ref['color']}")

    # Annotate part_ref so the grouped layout summary can use these fields later
    part_ref["part_name"]  = part_name
    part_ref["part_desc"]  = part_desc
    part_ref["desc_color"] = desc_color

    phrases = _PHRASES[mode]
    return _TMPL_PIECE.format(
        piece_intro   = phrases["piece_intro"],
        piece_idx     = piece_idx,
        part_name     = part_name,
        part_desc     = part_desc,
        desc_color    = desc_color,
        placement     = phrases["placement"],
        desc_rotation = describe_rotation(part_ref["rotation"], mode),
        desc_position = describe_position(part_ref["position"], mode),
    )

def describe_model(conn: sqlite3.Connection, model_name: str, grammar_contents: str, model_contents: str, mode: str):
    """Parse a LDraw model file and output a description suitable for an LLM to learn how to build the model, or how it looks."""

    phrases = _PHRASES[mode]

    load_colors_table(conn)

    semantic_model = parse_model_semantic(model_contents, grammar_contents)

    print(_TMPL_MODEL_HEADER.format(
        model_name     = model_name,
        intention      = phrases["intention"],
        model_contents = model_contents,
    ))

    all_pieces        = []
    submodel_contents = filter_submodels(semantic_model)

    for idx, item in enumerate(submodel_contents):
        if "header" in item:
            header = item["header"]
            names  = [h["name"]        for h in header if "name"        in h]
            descs  = [h["description"] for h in header if "description" in h]
            submodel_name = names[0] if names else f"Submodel {idx + 1}"
            submodel_desc = descs[0] if descs else "(ummm... no description?)"

            print(_TMPL_SUBMODEL_HEADER.format(
                submodel_num  = idx + 1,
                submodel_name = submodel_name,
                verb          = phrases["verb"],
                submodel_desc = submodel_desc,
            ))

        if "body" in item:
            for sub_idx, sub_item in enumerate(item["body"]):
                if "part" in sub_item:
                    part_ref = sub_item["part"]
                    part_ref["piece_idx"] = f"{idx + 1}.{sub_idx + 1}"
                    all_pieces.append(part_ref)
                    print(describe_part_ref(conn, part_ref, mode))
                    print("-----")

    print(_TMPL_OVERALL.format(overall_description=describe_grouped_pieces(all_pieces)))
    print(f"\n{phrases['finish']}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "-g", "--grammar",
    type=click.Path(file_okay=True, dir_okay=False, readable=True, writable=False, exists=True, resolve_path=True),
    help="Get lark grammar for parsing models and name and description extraction. If not provided it uses the one on LDRAW_GRAMMAR env variable.",
    envvar="LDRAW_GRAMMAR",
    required=True,
)
@click.option(
    "-m", "--model",
    type=click.Path(file_okay=True, dir_okay=True, readable=True, writable=True, exists=True, resolve_path=True),
    help="Get name and description from matching LDraw model/part FILE or models/parts under DIR (recursive).",
    required=True,
)
@click.option(
    "-d", "--db",
    type=click.Path(file_okay=True, dir_okay=False, readable=True, writable=True, exists=True, resolve_path=True),
    help="SQLite DB file to write the output to. Output will be also printed to stdout.",
    required=True,
)
@click.option(
    "--description-type",
    required=True, default="instructions",
    type=click.Choice(["instructions", "layout"], case_sensitive=False),
    help="Type of description to generate for the model: instructions (how to build it) or layout (how it looks), default: instructions",
)
def main(grammar, model, db, description_type):
    """Parse a LDraw model file and output a description suitable for an LLM to learn how to build the model, or how it looks."""

    mode    = description_type.lower()

    for path, label in [
        (grammar,     "grammar"),
        (model,       "model"),
        (db,          "database"),
    ]:
        if not os.path.isfile(path):
            print(f"Error: {label} file does not exist: {path}", file=sys.stderr)
            sys.exit(1)

    grammar     = os.path.abspath(grammar)
    model       = os.path.abspath(model)
    db          = os.path.abspath(db)

    with open(grammar, "r", encoding="utf-8") as f:
        grammar_contents = f.read()

    with open(model, "r", encoding="utf-8", errors="replace") as f:
        model_contents = f.read()

    with sqlite3.connect(db) as conn:
        configure_sqlite(conn)

        describe_model(conn, os.path.basename(model), grammar_contents, model_contents, mode)


if __name__ == "__main__":
    main()

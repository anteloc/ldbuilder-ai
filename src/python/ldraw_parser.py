from lark import Lark, Tree, Token, Transformer, v_args
import json
import yaml
import os
import click
import sys
from typing import List, Dict

# Conditionally import ldrawmath - not needed for unparsing
try:
    from python.ldraw_math import ldraw_type1_matrix_to_euler_yxz
except ImportError:
    ldraw_type1_matrix_to_euler_yxz = None

# Get grammars directory from environment variable or default to sibling grammars/ directory where grammars are assumed to be
GRAMMARS_DIR = os.environ.get(
    "GRAMMARS_DIR", os.path.join(os.path.dirname(__file__), "..", "grammars")
)
GRAMMARS_DIR = os.path.abspath(GRAMMARS_DIR)


# ---------------------------------------------------------------------------
# Forward (parse) transformers
# ---------------------------------------------------------------------------

class SemanticTransformer(Transformer):
    step_counter = 0

    def color(self, items):
        return items[0].value

    def point(self, items):
        return [float(coord.value) for coord in items]

    def position(self, items):
        return self.point(items)

    def matrix(self, items):
        elements = [float(comp.value) for comp in items]
        return [
            elements[0:3],
            elements[3:6],
            elements[6:9],
        ]

    def file_ref(self, items):
        return str(items[0])

    def file_line(self, items):
        return {"file": items[1].value}

    def meta_line(self, items):
        return {"meta": items[1].value if len(items) > 1 else ""}

    def description_line(self, items):
        return {"description": items[1].value}

    def name_line(self, items):
        return {"name": items[1].value}

    def author_line(self, items):
        return {"author": items[1].value}

    def ldraw_org_line(self, items):
        return {"ldraw_org": items[1].value}

    def license_line(self, items):
        return {"license": items[1].value}

    def part_line(self, items):
        rotation = ldraw_type1_matrix_to_euler_yxz(items[3]) if ldraw_type1_matrix_to_euler_yxz else [0.0, 0.0, 0.0]
        return {
            "part": {
                "color": items[1],
                "position": items[2],
                "matrix": items[3],
                "rotation": list(rotation),
                "file_ref": items[4],
            }
        }

    def line_line(self, items):
        return {
            "line": {
                "color": items[1],
                "p1": items[2],
                "p2": items[3],
            }
        }

    def tri_line(self, items):
        return {
            "triangle": {
                "color": items[1],
                "p1": items[2],
                "p2": items[3],
                "p3": items[4],
            }
        }

    def quad_line(self, items):
        return {
            "quad": {
                "color": items[1],
                "p1": items[2],
                "p2": items[3],
                "p3": items[4],
                "p4": items[5],
            }
        }

    def cond_line(self, items):
        return {
            "cond": {
                "color": items[1],
                "p1": items[2],
                "p2": items[3],
                "p3": items[4],
                "p4": items[5],
            }
        }

    def step_line(self, items):
        self.step_counter += 1
        return {"step": self.step_counter}

    def subfile(self, items):
        return {"subfile": items}

    def subfile_header(self, items):
        return {"header": items}

    def plain_header(self, items):
        return self.subfile_header(items)

    def body(self, items):
        return {"body": items}

    def mpd_model(self, items):
        return {"type": "mpd", "model": items}

    def plain_model(self, items):
        return {"type": "plain", "model": items}

    def start(self, items):
        return items[0]


# ---------------------------------------------------------------------------
# JSON grammar for parsing semantic AST JSON strings
# ---------------------------------------------------------------------------
# Following the Lark JSON tutorial approach:
#   https://lark-parser.readthedocs.io/en/stable/json_tutorial.html
#
# This is a standard JSON grammar. The UnparseTransformer first reduces
# the JSON parse tree to native Python objects (dicts/lists), then walks
# the semantic structure to emit LDraw lines.

_JSON_GRAMMAR = r"""
    start: value

    ?value: object
          | array
          | string
          | SIGNED_NUMBER  -> number
          | "true"         -> true
          | "false"        -> false
          | "null"         -> null

    array  : "[" [value ("," value)*] "]"
    object : "{" [pair ("," pair)*] "}"
    pair   : string ":" value

    string : ESCAPED_STRING

    %import common.ESCAPED_STRING
    %import common.SIGNED_NUMBER
    %import common.WS

    %ignore WS
"""


# ---------------------------------------------------------------------------
# Reverse (unparse) transformer
# ---------------------------------------------------------------------------

class UnparseTransformer(Transformer):
    """Transform a Lark JSON parse-tree of a semantic AST into LDraw text lines.

    Following the Lark JSON tutorial pattern, this Transformer works on the Tree
    produced by parsing the semantic AST JSON string with a standard JSON grammar.

    The bottom-up transformation first reduces JSON nodes (object, array, pair,
    string, number) into native Python objects (dicts, lists, strings, floats).
    The top-level ``start`` rule then walks the resulting semantic dict to emit
    the final list of LDraw text lines.
    """

    # -- JSON primitive reductions (identical to the Lark JSON tutorial) --

    @v_args(inline=True)
    def string(self, s):
        return s[1:-1].replace('\\"', '"').replace('\\\\', '\\')

    @v_args(inline=True)
    def number(self, n):
        f = float(n)
        # Preserve int-ness when the JSON literal has no decimal point
        if f == int(f) and '.' not in str(n) and 'e' not in str(n).lower():
            return int(n)
        return f

    array = list
    pair = tuple
    object = dict

    def null(self, _):
        return None

    def true(self, _):
        return True

    def false(self, _):
        return False

    # -- Top-level entry: the tree has been fully reduced to a Python dict --

    def start(self, items):
        """Convert the fully-reduced semantic AST dict into LDraw text lines."""
        sem_ast = items[0]
        return _sem_ast_to_lines(sem_ast)


# ---------------------------------------------------------------------------
# Semantic AST dict  →  LDraw text lines
# ---------------------------------------------------------------------------

def _format_number(n):
    """Format a number for LDraw output: whole floats become ints."""
    if isinstance(n, float):
        if n == int(n):
            return str(int(n))
        return str(n)
    return str(n)


def _sem_ast_to_lines(sem_ast: dict) -> list:
    """Convert a semantic AST dict (as produced by SemanticTransformer) to LDraw text lines."""
    lines = []

    node_type = sem_ast.get("type")
    if node_type in ("mpd", "plain"):
        for model_entry in sem_ast.get("model", []):
            _unparse_subfile(model_entry, lines)
    else:
        _unparse_subfile(sem_ast, lines)

    return lines


def _unparse_subfile(subfile_dict: dict, lines: list):
    """Unparse a subfile dict (which contains 'subfile' key with [header, body])."""
    subfile_parts = subfile_dict.get("subfile", [])
    for part in subfile_parts:
        if "header" in part:
            _unparse_header(part["header"], lines)
        elif "body" in part:
            _unparse_body(part["body"], lines)


def _unparse_header(header_items: list, lines: list):
    """Unparse header items into LDraw type-0 lines."""
    for item in header_items:
        if "file" in item:
            lines.append(f"0 FILE {item['file']}")
        elif "description" in item:
            lines.append(f"0 {item['description']}")
        elif "name" in item:
            lines.append(f"0 Name: {item['name']}")
        elif "author" in item:
            lines.append(f"0 Author: {item['author']}")
        elif "ldraw_org" in item:
            lines.append(f"0 !LDRAW_ORG {item['ldraw_org']}")
        elif "license" in item:
            lines.append(f"0 !LICENSE {item['license']}")
        elif "meta" in item:
            lines.append(f"0 {item['meta']}")
        elif "step" in item:
            lines.append("0 STEP")


def _unparse_body(body_items: list, lines: list):
    """Unparse body items into LDraw lines."""
    for item in body_items:
        if "part" in item:
            _unparse_part(item["part"], lines)
        elif "line" in item:
            _unparse_line_type2(item["line"], lines)
        elif "triangle" in item:
            _unparse_tri(item["triangle"], lines)
        elif "quad" in item:
            _unparse_quad(item["quad"], lines)
        elif "cond" in item:
            _unparse_cond(item["cond"], lines)
        elif "step" in item:
            lines.append("0 STEP")
        elif "meta" in item:
            lines.append(f"0 {item['meta']}")


def _unparse_part(part: dict, lines: list):
    """Unparse a part (Line Type 1) reference.

    Format: 1 <colour> x y z a b c d e f g h i <file>

    The matrix in the semantic AST is stored as 3x3 rows:
      [[a, b, c], [d, e, f], [g, h, i]]
    which maps directly to the LDraw line format: a b c d e f g h i
    """
    color = part["color"]
    pos = part["position"]
    matrix = part["matrix"]
    file_ref = part["file_ref"]

    pos_str = " ".join(_format_number(v) for v in pos)
    mat_str = " ".join(_format_number(v) for row in matrix for v in row)

    lines.append(f"1 {color} {pos_str} {mat_str} {file_ref}")


def _unparse_line_type2(prim: dict, lines: list):
    """Unparse a Line Type 2 (line between two points)."""
    color = prim["color"]
    p1 = " ".join(_format_number(v) for v in prim["p1"])
    p2 = " ".join(_format_number(v) for v in prim["p2"])
    lines.append(f"2 {color} {p1} {p2}")


def _unparse_tri(prim: dict, lines: list):
    """Unparse a Line Type 3 (triangle)."""
    color = prim["color"]
    p1 = " ".join(_format_number(v) for v in prim["p1"])
    p2 = " ".join(_format_number(v) for v in prim["p2"])
    p3 = " ".join(_format_number(v) for v in prim["p3"])
    lines.append(f"3 {color} {p1} {p2} {p3}")


def _unparse_quad(prim: dict, lines: list):
    """Unparse a Line Type 4 (quadrilateral)."""
    color = prim["color"]
    p1 = " ".join(_format_number(v) for v in prim["p1"])
    p2 = " ".join(_format_number(v) for v in prim["p2"])
    p3 = " ".join(_format_number(v) for v in prim["p3"])
    p4 = " ".join(_format_number(v) for v in prim["p4"])
    lines.append(f"4 {color} {p1} {p2} {p3} {p4}")


def _unparse_cond(prim: dict, lines: list):
    """Unparse a Line Type 5 (conditional line)."""
    color = prim["color"]
    p1 = " ".join(_format_number(v) for v in prim["p1"])
    p2 = " ".join(_format_number(v) for v in prim["p2"])
    p3 = " ".join(_format_number(v) for v in prim["p3"])
    p4 = " ".join(_format_number(v) for v in prim["p4"])
    lines.append(f"5 {color} {p1} {p2} {p3} {p4}")


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------

def parse_model_semantic(model_contents: str, grammar_contents: str):
    ast_tree = parse_model_ast(model_contents, grammar_contents)
    semantic = SemanticTransformer().transform(ast_tree)
    return semantic


def parse_model_ast(model_contents: str, grammar_contents: str) -> Tree:
    parser = Lark(
        grammar_contents,
        parser="lalr",
        maybe_placeholders=False,
        debug=False,
        propagate_positions=True,
    )
    tree = parser.parse(model_contents)
    return tree


def unparse_model_semantic(sem_ast_json: str, grammar_contents: str) -> list:
    """Unparse a semantic AST JSON string back to LDraw model text lines.

    Following the Lark JSON tutorial approach:
      1. Parse the JSON string using a JSON grammar  →  Lark Tree
      2. Transform the Tree with UnparseTransformer   →  list[str] of LDraw lines

    Args:
        sem_ast_json: JSON string representing the semantic AST
        grammar_contents: Contents of the ldraw-unparse.lark grammar file
                         (a standard JSON grammar)

    Returns:
        List of strings, each representing one line of LDraw output
    """
    # Step 1: Parse the JSON string into a Lark Tree
    json_tree = unparse_model_ast(sem_ast_json, grammar_contents)

    # Step 2: Transform the tree into LDraw output lines
    lines = UnparseTransformer().transform(json_tree)

    return lines


def unparse_model_ast(sem_ast_json: str, grammar_contents: str) -> Tree:
    """Parse a semantic AST JSON string into a Lark Tree using the JSON grammar.

    Args:
        sem_ast_json: JSON string representing the semantic AST
        grammar_contents: Contents of the ldraw-unparse.lark grammar file

    Returns:
        Lark Tree representing the parsed JSON structure
    """
    parser = Lark(
        grammar_contents,
        parser="lalr",
        maybe_placeholders=False,
        debug=False,
    )
    tree = parser.parse(sem_ast_json)
    return tree


# ---------------------------------------------------------------------------
# Convenience: direct unparse from dict (no grammar / Lark needed)
# ---------------------------------------------------------------------------

def unparse_from_dict(sem_ast: dict) -> str:
    """Convenience function: unparse a semantic AST dict directly to LDraw text.

    This bypasses the JSON grammar parsing step and works directly on a
    Python dict (e.g., loaded via json.loads()).

    Args:
        sem_ast: Python dict representing the semantic AST

    Returns:
        LDraw model text as a string
    """
    lines = _sem_ast_to_lines(sem_ast)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    pass


@cli.command()
@click.option(
    "--grammars-dir", help="Directory where grammars are located", default=GRAMMARS_DIR
)
def grammars(grammars_dir):
    """List available grammars."""
    print("Available grammars:")
    print(f"Located under directory: {grammars_dir}")
    available_grammars = [f for f in os.listdir(grammars_dir) if f.endswith(".lark")]
    if available_grammars:
        for g in available_grammars:
            print(f" - {g}")
        exit(0)


@cli.command()
@click.option(
    "--grammar",
    "-g",
    help="Grammar filename used to unparse the model semantic AST in JSON format, located under grammars directory",
    required=True,
)
@click.option(
    "--ast-json", "-a", help="Path to JSON file containing the semantic AST to unparse", required=True
)
@click.option(
    "--grammars-dir", help="Directory where grammars are located", default=GRAMMARS_DIR
)
def unparse(grammar, ast_json, grammars_dir):
    """Unparse an LDraw model file using the specified unparsing Lark grammar.

    Output types:
    A LDraw model in text format, equivalent to the original parsed .ldr, .mpd or .dat file,
    but generated from the semantic AST in JSON format. The output will be printed to stdout.
    """

    grammars_dir = os.path.abspath(grammars_dir)
    grammar_path = os.path.join(grammars_dir, grammar)

    print(f"Using grammar file: {grammar_path}", file=sys.stderr)

    if not os.path.isdir(grammars_dir):
        print(f"Error: grammars directory does not exist: {grammars_dir}", file=sys.stderr)
        exit(1)
    if not os.path.isfile(grammar_path):
        print(f"Error: grammar file does not exist: {grammar_path}", file=sys.stderr)
        exit(1)

    with open(grammar_path, "r", encoding="utf-8") as f:
        grammar_contents = f.read()

    # Read AST JSON — support both file path and inline JSON string
    if os.path.isfile(ast_json):
        with open(ast_json, "r", encoding="utf-8") as f:
            ast_json_str = f.read()
    else:
        ast_json_str = ast_json

    print(f"----- Unparsing model from AST JSON", file=sys.stderr)

    unparsed = unparse_model_semantic(ast_json_str, grammar_contents)

    unparsed_model = "\n".join(unparsed) + "\n"

    print(unparsed_model, end="")


@cli.command()
@click.option(
    "--grammar",
    "-g",
    help="Grammar filename, if not set, must be provided via LDRAW_GRAMMAR environment variable",
    envvar="LDRAW_GRAMMAR",
    required=True,
)
@click.option(
    "--model", "-m", help="LDraw model file to parse: .ldr, .mpd, .dat", required=True
)
@click.option(
    "--output",
    "-o",
    help="Output type, one of: ast (default), sem (semantic)",
    default="ast",
)
@click.option(
    "--format",
    "-f",
    help="Output format for the parsed syntax tree, one of: json (default), yaml, text",
    default="json",
)
@click.option(
    "--grammars-dir", help="IGNORED - Directory where grammars are located", default=GRAMMARS_DIR
)
@click.option("-q", "--quiet", is_flag=True, help="Suppress informational output to stdout")
def parse(grammar, model, output, format, grammars_dir, quiet):
    """Parse an LDraw model file using the specified Lark grammar.

    Output types:

    - ast: Output an AST (Abstract Syntax Tree) tree built from the model against the grammar.

    - semantic: Output a 'semantic tree' (i.e., a tree representing the semantic structure)
      built from the model against the grammar.
    """

    grammars_dir = os.path.abspath(grammars_dir)
    grammar_path = os.path.abspath(grammar)
    # grammar_path = os.path.join(grammars_dir, grammar)
    model_path = os.path.abspath(model)

    if not quiet:
        print(f"Using grammar file: {grammar_path}", file=sys.stderr)
        print(f"Using model file: {model_path}", file=sys.stderr)

    # if not os.path.isdir(grammars_dir):
    #     print(f"Error: grammars directory does not exist: {grammars_dir}", file=sys.stderr)
    #     exit(1)
    if not os.path.isfile(model_path):
        print(f"Error: model file does not exist: {model}", file=sys.stderr)
        exit(1)
    if not os.path.isfile(grammar_path):
        print(f"Error: grammar file does not exist: {grammar_path}", file=sys.stderr)
        exit(1)

    with open(grammar_path, "r", encoding="utf-8") as f:
        grammar_contents = f.read()

    with open(model_path, "r", encoding="utf-8", errors="replace") as f:
        model_contents = f.read()

    print(f"----- Parsing model: {model_path}", file=sys.stderr)

    tree: Tree | None = None
    output_str = None

    if output == "sem":
        sem_tree = parse_model_semantic(model_contents, grammar_contents)
        if isinstance(sem_tree, Tree):
            output_str = sem_tree.pretty()
        else:
            if format == "yaml":
                output_str = yaml.dump(sem_tree, sort_keys=False)
            elif format == "json":
                output_str = json.dumps(sem_tree, ensure_ascii=False, indent=2)
    else:
        tree = parse_model_ast(model_contents, grammar_contents)
        output_str = tree.pretty()

    print(output_str)


if __name__ == "__main__":
    cli()

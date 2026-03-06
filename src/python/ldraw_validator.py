#!/usr/bin/env python
from __future__ import annotations

import sys
import traceback

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
from typing import Any, Iterable
from ldraw_parser import parse_model_semantic
# WIP will validate also contacts
# from ldraw_contact_pieces import run_contact_pieces
from functools import lru_cache
import ldraw_parse_model as lpm

import click
import sqlite3

def configure_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")

LDRAW_EXTS = {".ldr", ".dat", ".mpd"}

def iter_ldraw_files(paths: Iterable[str]) -> Iterable[Path]:
    for p in map(Path, paths):
        if p.is_file():
            yield p.resolve()
        elif p.is_dir():
            yield from (
                f.resolve()
                for f in p.rglob("*")
                if f.is_file() and f.suffix.lower() in LDRAW_EXTS
            )

class LDrawValidator:
    grammar_contents: str
    conn: sqlite3.Connection

    def __init__(self, grammar_contents: str, conn: sqlite3.Connection):
        self.grammar_contents = grammar_contents
        self.conn = conn

    @lru_cache(maxsize=200_000)
    def part_info(self, alias: str) -> dict[str, str]:
        """
        Returns the part info for the given alias, including the name and description from the database, or "missing" if not available.
        """

        # test several combinations: depending on the source of the alias, it could be Windows-style, Unix-style, escaped backslashes, etc.
        unix_alias_1 = alias.replace("\\", "/")
        unix_alias_2 = alias.replace("\\\\", "/")
        win_alias_1 = alias.replace("/", "\\")
        win_alias_2 = alias.replace("/", "\\\\")

        cur = self.conn.execute("""
                                SELECT alias, name, description
                                FROM PART_INFOS PI 
                                WHERE UPPER(PI.alias) IN (UPPER(?), UPPER(?), UPPER(?), UPPER(?))
                                """, (unix_alias_1, unix_alias_2, win_alias_1, win_alias_2))
        row = cur.fetchone()
        cur.close()
        if row:
            return {
                    "alias": row[0],
                    "name": row[1],
                    "description": row[2]
                }
        else:
            return { "missing": alias }
        
    def validate_refs_and_colors(self, model_name: str, submodels: list[lpm.SubModel]) -> dict[str, Any]:
        refs_errors = []

        for sm in submodels:
            # validate only external subfile references, i.e. those will be valid if they exist in the database,
            # which is a source of truth for valid external files, e.g. the ones in official ldraw library or other extra paths
            extSubfileRefs = [pr.fileRef for pr in sm.partRefs if not pr.internal]

            for sfr in extSubfileRefs:
                # validate both valid part (it exists in the database) and valid color (it exists in the COLORS table)
                errs = []
                # FIXME validate internal refs, files ending in other than .dat
                part_info = self.part_info(sfr.ref)
                part_color = COLORS_TABLE.get(sfr.color, None)

                if "missing" in part_info:
                    errs.append(f"Unknown part: {sfr.ref}")
                if part_color is None:
                    errs.append(f"Invalid color: {sfr.color}")

                if errs:
                    refs_errors.append({
                        "line": str(sfr),
                        "errors": errs
                    })

        # TODO still WIP, collision detection currently doesn't work with DB, it requires ldraw_dir, wich is very slow and inconvenient
        # contacts_json = run_contact_pieces(model.as_posix(), output_format="json", ext_db_conn=self.conn)
        # contacts = json.loads(contacts_json)

        return {
            "model": model_name,
            "errors": refs_errors,
        }

    
    def process(self, model: Path) -> dict[str, Any]:
        click.echo(f"'{model.name}': processing", err=True)

        model_contents = model.read_text(encoding="utf-8")

        # semantic parsing, which includes syntax parsing under the hood
        try:
            sem_tree = parse_model_semantic(model_contents, self.grammar_contents)
            click.echo(f"'{model.name}': semantic parsing successful", err=True)
        except Exception as e:
            # early return: it doesn't make sense to continue validating if the model has syntax errors or other parsing errors, 
            # as the rest of the validation relies on a correct semantic tree
            return {
                "model": model.name,
                "errors": [f"Parsing error: {type(e).__name__}: {e}"],
            }

        # build model representation, it will validate other things like e.g. correct values
        mpdModel = lpm.MPDModel(sem_tree)
        click.echo(f"'{model.name}': model representation built", err=True)

        submodels: list[lpm.SubModel] = mpdModel.subModels

        return self.validate_refs_and_colors(model.name, submodels)
    
COLORS_TABLE: dict[str, str] = {}

def _load_colors_table(conn: sqlite3.Connection) -> None:
    global COLORS_TABLE
    cur = conn.execute("SELECT code, color FROM COLORS")
    # get row fields by name, and build a dict of code to name
    COLORS_TABLE = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()

_WORKER_EXTRACTOR: LDrawValidator | None = None

def _init_worker(grammar_contents: str, db_path: str) -> None:
    global _WORKER_EXTRACTOR
    conn = sqlite3.connect(db_path)
    configure_sqlite(conn)
    _load_colors_table(conn)
    _WORKER_EXTRACTOR = LDrawValidator(
        grammar_contents=grammar_contents,
        conn=conn,
    )

def _process_file(path_str: str) -> tuple[Path | None, dict, str | None]:
    if _WORKER_EXTRACTOR is None:
        raise RuntimeError("Worker extractor not initialized")
    p = Path(path_str)
    try:
        return p, _WORKER_EXTRACTOR.process(p), None
    except Exception as e:
        # Convert to string immediately — some exceptions (e.g. from Lark) are not
        # pickleable and would cause executor.map to silently drop the result entirely.
        tb = traceback.format_exc()
        return p, {}, f"{type(e).__name__}: {e}\n{tb}"


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "-f", "--filepath",
    type=click.Path(file_okay=True, dir_okay=True, readable=True, writable=True, exists=True, resolve_path=True),
    help="Get name and description from matching LDraw model/part FILE or models/parts under DIR (recursive).",
    required=True,
)

@click.option(
    "-g", "--grammar",
    type=click.Path(file_okay=True, dir_okay=False, readable=True, writable=False, exists=True, resolve_path=True),
    help="Get lark grammar for parsing models and name and description extraction. If not provided it uses the one on LDRAW_GRAMMAR env variable.",
    envvar="LDRAW_GRAMMAR",
    required=True,
)

@click.option(
    "-d", "--db",
    type=click.Path(file_okay=True, dir_okay=False, readable=True, writable=True, exists=True, resolve_path=True),
    help="SQLite DB file to write the output to. Output will be also printed to stdout.",
    required=True,
)

@click.option(
    "-w", "--workers",
    type=int,
    default=max(1, os.cpu_count() or 1),
    show_default=True,
    help="Number of worker processes to parse files. Use 1 to disable multiprocessing.",
)
def main(
    filepath: str,
    grammar: str,
    db: str,
    workers: int,
) -> None:
    """Example usage:
    # Validate a single model file:
    pypy3 ldraw-validator.py --grammar ./ldraw.lark --db ldraw-info.db --filepath some-model.(mpd,ldr,dat)

    # Validate model files under a directory (recursively):
    pypy3 ldraw-validator.py --grammar ./ldraw.lark --db ldraw-info.db --filepath some-models-dir/
    """

    p_filepath = Path(filepath)
    p_grammar = Path(grammar)
    p_db = Path(db)
    workers = max(1, workers) # avoid negative or zero workers

    # verify that the input paths exist and are of the correct type
    if not p_filepath.exists():
        click.echo(f"Error: Filepath '{p_filepath}' does not exist.", err=True)
        return
    if not p_grammar.is_file():
        click.echo(f"Error: Grammar file '{p_grammar}' does not exist or is not a file.", err=True)
        return
    if not p_db.is_file():
        click.echo(f"Error: DB file '{p_db}' does not exist or is not a file.", err=True)
        return

    click.echo(f"Validating: '{p_filepath.as_posix()}'", err=True)
    
    grammar_contents = p_grammar.read_text(encoding="utf-8")

    with sqlite3.connect(p_db) as conn:
        configure_sqlite(conn)

        files = [fp.as_posix() for fp in iter_ldraw_files([filepath])]

        print(f"Found {len(files)} files to validate.", file=sys.stderr)

        try:
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_init_worker,
                initargs=(grammar_contents, str(p_db)),
            ) as executor:
                futures = {executor.submit(_process_file, fp): fp for fp in files}
                for future in as_completed(futures):
                    p_model, model_errors, err = future.result()
                    res = {
                        "model_file": p_model.as_posix(),
                    }
                    
                    msg = ""

                    if err:
                        msg = f"ERROR processing: {err}"
                        res["failed"] = [err]
                    elif model_errors.get("errors"):
                        msg = "ERROR validating model"
                        res["failed"] = model_errors["errors"]
                    else:
                        msg = "OK"

                    res["status"] = msg

                    print(json.dumps(res))
                        
        except PermissionError as pe:
            click.echo(f"Permission error while processing model: {pe}", err=True)
        except Exception:
            print(traceback.format_exc(), file=sys.stderr)

if __name__ == "__main__":
    main()
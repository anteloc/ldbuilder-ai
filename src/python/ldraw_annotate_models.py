#!/usr/bin/env python
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import json
import logging
import math
import os
from pathlib import Path
import time
from typing import Iterable
from ldraw_parser import parse_model_semantic
# from ldraw_contact_pieces import run_contact_pieces

from ldraw_contacts import detect as detect_contacts

from functools import lru_cache
import ldraw_parse_model as lpm

import click
import sqlite3

def round_to_half(n):
    """Round to nearest 0.5 or integer."""
    return round(n * 2) / 2

def vector_angles(x, y):
    angle_with_x = math.atan2(y, x)  # radians
    angle_with_y = math.atan2(x, y)  # radians
    return math.degrees(angle_with_x), math.degrees(angle_with_y)

def classify_direction(vec: dict[str, float]) -> str:
    """
    Classifies a direction based on angle from X-axis (degrees).
    Angle assumed counter-clockwise from +X axis.
    """
    # Calculate angle from X-axis, taking into account that Y is inverted (negative upward)
    x_angle, _ = vector_angles(vec["x"], -vec["y"])

    # Normalize angle to [0, 360)
    angle = x_angle % 360

    if 337.5 <= angle or angle < 22.5:
        return "right"
    elif 22.5 <= angle < 67.5:
        return "top-right"
    elif 67.5 <= angle < 112.5:
        return "top"
    elif 112.5 <= angle < 157.5:
        return "top-left"
    elif 157.5 <= angle < 202.5:
        return "left"
    elif 202.5 <= angle < 247.5:
        return "bottom-left"
    elif 247.5 <= angle < 292.5:
        return "bottom"
    else:  # 292.5 <= angle < 337.5
        return "bottom-right"
    

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

def verify_table_exists(conn: sqlite3.Connection, table_name: str) -> None:
    """Verify that the given table exists, raise exception otherwise."""
    cur = conn.execute(
        f"""
        SELECT EXISTS (
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = '{table_name}' COLLATE NOCASE
        );
        """
    )

    exists = cur.fetchone()[0]
    cur.close()

    if not exists:
        raise ValueError(f"Required table '{table_name}' does not exist in the database.")

def configure_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.row_factory = sqlite3.Row

def insert_model_descriptions(
    conn: sqlite3.Connection,
    records: list[dict],
    table_name: str,
) -> None:
    sql = f"""
        INSERT INTO {table_name} (alias, name, description)
        VALUES (:alias, :name, :description)
    """

    try:
        conn.executemany(sql, records)
    except Exception as e:
        logging.error("Failed to insert records batch: %s", e)


@dataclass(frozen=True)
class LDrawAnnotator:
    grammar_contents: str
    conn: sqlite3.Connection

    @lru_cache(maxsize=200_000)
    def part_info_bbox(self, alias: str) -> tuple[dict[str, str], dict[str, str | float]]:
        """
        Returns the part info for the given alias, including the name and description from the database, or "missing" if not available.
        """

        # test several combinations: depending on the source of the alias, it could be Windows-style, Unix-style, escaped backslashes, etc.
        unix_alias = alias.replace("\\", "/") # in some instances, this will generate unix_alias_1="48//some_part.dat"
        sanitized_alias = unix_alias.replace("//", "/") # this we will take as reference: the sanitize

        win_alias_1 = alias.replace("/", "\\")
        win_alias_2 = alias.replace("/", "\\\\")

        cur = self.conn.execute(f"""
                                    SELECT '{sanitized_alias}' as alias, name, description
                                    FROM PART_INFOS PI 
                                    WHERE UPPER(PI.alias) IN (UPPER(?), UPPER(?), UPPER(?), UPPER(?))
                                """, (unix_alias, sanitized_alias, win_alias_1, win_alias_2))
        p_info = cur.fetchone()
        cur.close()

        cur = self.conn.execute("""
                                    SELECT *
                                    FROM PART_BBOXES
                                    WHERE alias = ?
                                """, (sanitized_alias,))
        
        p_bbox = cur.fetchone()
        cur.close()

        p_info = p_info if p_info else {}
        p_bbox = p_bbox if p_bbox else {}

        return dict(p_info), dict(p_bbox)
    
    def _annotate_part_info_meta(self, partRef: lpm.PartRef, subModel: lpm.SubModel, mpdModel: lpm.MPDModel) -> None:
        # 0 !P P1.3 'Car Base  4 x  5' 'Yellow' front-facing,upward-facing,upright 80x20x100 LDU
        pid: str
        color_name: str
        orientation: str
        description: str
        dimensions: str

        def dimensions_str(p_bbox: dict[str, str | float]) -> str:
            w = round_to_half(p_bbox.get("dim_x", 0))
            h = round_to_half(p_bbox.get("dim_y", 0))
            d = round_to_half(p_bbox.get("dim_z", 0))
            return f"{w:.10g}x{h:.10g}x{d:.10g}"

        fileRef = partRef.fileRef

        pid = f"P{fileRef.globalOrdinal}"
        color_name = COLORS_TABLE.get(fileRef.color, f"Color{fileRef.color}")
        orientation = ",".join(partRef.orientation)

        # search for the information on the DB for references to external parts
        if not partRef.internal:
            p_info, p_bbox = self.part_info_bbox(fileRef.ref)
            description = p_info.get("description", "(missing description)")
            dimensions = dimensions_str(p_bbox) if p_bbox else "(missing dimensions)"
        else:
            description = fileRef.ref # set for internal references, better than duplicating description from the referenced subModel
            dimensions = "N/A"

        partInfoMeta = lpm.PartInfoMeta(
            pid=pid,
            description=description,
            colorName=color_name,
            orientation=orientation,
            dimensions=dimensions,
        )
            
        mpdModel.setPartInfoMeta(partRef, partInfoMeta, subModel)

    def _annotate_part_touches_meta(self, partRef: lpm.PartRef, subModel: lpm.SubModel, mpdModel: lpm.MPDModel, contacts_idx: dict) -> None:
        # 0 !TOUCHES ⚠️P2@bottom-left P4@top-right P5@right P6@left P7@bottom ⚠️P8@top P9@bottom-right P10@bottom
        ord = partRef.fileRef.globalOrdinal
        part_contacts = contacts_idx.get(ord, [])
        
        if not part_contacts:
            return
        
        pids = []
        intersects = set()
        rel_pos = {}
        
        for pc in part_contacts:
            pc_pid = pc["pid"]
            pc_vec = pc["vector"]
            pc_inters = pc["intersects"]
            pc_rel_pos = classify_direction(pc_vec)

            pid = f"P{pc_pid}"
            pids.append(pid)

            if pc_inters:
                intersects.add(pid)
            
            rel_pos[pid] = pc_rel_pos

        partTouchesMeta = lpm.PartTouchesMeta(
            pids=pids,
            intersects=intersects,
            relPositions=rel_pos,
        )

        mpdModel.setPartTouchesMeta(partRef, partTouchesMeta, subModel)
        
    def annotate_part(self, partRef: lpm.PartRef, subModel: lpm.SubModel, mpdModel: lpm.MPDModel, contacts_idx: dict) -> None:
        # Annotate the given part by filling in information so the end result will be something like e.g.:
        # 0 !P P1 'Car Base  4 x  5' 'Yellow' front-facing,upward-facing,upright 80x20x100 LDU
        # 0 !TOUCHES ⚠️P2@bottom-left P4@top-right P5@right P6@left P7@bottom ⚠️P8@top P9@bottom-right P10@bottom
        # 1 14 80 -384 340 0 0 -1 0 1 0 1 0 0 3001.dat
        self._annotate_part_info_meta(partRef, subModel, mpdModel)
        self._annotate_part_touches_meta(partRef, subModel, mpdModel, contacts_idx)
        
    def annotate_parts(self, subModel: lpm.SubModel, mpdModel: lpm.MPDModel, contacts_idx: dict) -> None:
        for partRef in subModel.partRefs:
            self.annotate_part(partRef, subModel, mpdModel, contacts_idx)
            

    def process(self, model: Path) -> str:
        model_contents = model.read_text(encoding="utf-8")
        sem_tree = parse_model_semantic(model_contents, self.grammar_contents)

        # FIXME we are not detecting collisions: when getting the info from DB and not ldraw_dir, it doesn't calculate collisions
        # contacts_json = run_contact_pieces(path=model.as_posix(), output_format="json", ext_db_conn=self.conn)
        # contacts = json.loads(contacts_json)

        contacts = detect_contacts(sem_tree, self.conn)

        # FIXME sometimes, there is no "pieces" key, it seems like contacts_json complains about not finding any type-1 line, 
        # but that is not accurate: there are type-1 lines, as psem_tree confirms
        contacts_idx = {p["pid"]: p["contacts"] for p in contacts.get("pieces", [])}

        # build model representation, it will validate other things like e.g. correct values
        mpdModel = lpm.MPDModel(sem_tree)
        
        for subModel in mpdModel.subModels:
            self.annotate_parts(subModel, mpdModel, contacts_idx)

        return str(mpdModel)
    
def _verify_required_tables(conn: sqlite3.Connection) -> None:
    required_tables = {"PART_INFOS", "PART_BBOXES", "COLORS"}
    for table in required_tables:
        verify_table_exists(conn, table)

COLORS_TABLE: dict[str, str] = {}

def _load_colors_table(conn: sqlite3.Connection) -> None:
    global COLORS_TABLE
    cur = conn.execute("SELECT code, color FROM COLORS")
    # get row fields by name, and build a dict of code to name
    COLORS_TABLE = {row['code']: row['color'] for row in cur.fetchall()}
    cur.close()

_WORKER_EXTRACTOR: LDrawAnnotator | None = None

def _init_worker(grammar_contents: str, db_path: str) -> None:
    global _WORKER_EXTRACTOR
    conn = sqlite3.connect(db_path)
    configure_sqlite(conn)
    _load_colors_table(conn)
    _WORKER_EXTRACTOR = LDrawAnnotator(
        grammar_contents=grammar_contents,
        conn=conn,
    )

def _process_file(path_str: str) -> tuple[Path, str | None, str | None]:
    if _WORKER_EXTRACTOR is None:
        raise RuntimeError("Worker extractor not initialized")
    p = Path(path_str)
    try:
        return p, _WORKER_EXTRACTOR.process(p), None
    except Exception as e:
        # Some exceptions (e.g. from Lark) are not pickleable; return a string instead.
        return p, None, f"{type(e).__name__}: {e}"

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "-f", "--filepath",
    type=click.Path(file_okay=True, dir_okay=True, readable=True, writable=True, exists=True, resolve_path=True),
    help="Get name and description from matching LDraw model/part FILE or models/parts under DIR (recursive).",
    required=True,
)
@click.option(
    "-o", "--output",
    type=click.Path(file_okay=False, dir_okay=True, readable=True, writable=True, resolve_path=True),
    help="Target destination directory, will be created if it does not exist. The annotated model(s) will be under this directory, with .ann.ldr, .ann.dat or .ann.mpd extension.",
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
@click.option(
    "--verbose/--quiet",
    default=False,
    show_default=True,
    help="Print per-file progress messages.",
)
def main(
    filepath: str,
    output: str,
    grammar: str,
    db: str,
    workers: int,
    verbose: bool,
) -> None:
    """Example usage:
    # Add the whole ldraw library, removing all the $ldraw_dir/parts, /p and full $ldraw_dir prefixes
    pypy3 $tools_dir/ldraw-annotate-models.py --grammar $lark_dir/grammars/ldraw.lark --db ldraw-info.db --filepath some/models-dir --output annotated-models-dir --workers 8
    """

    p_filepath = Path(filepath)
    p_grammar = Path(grammar)
    p_db = Path(db)
    p_output = Path(output)
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
    if not p_output.exists():
        try:
            p_output.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            click.echo(f"Error: Output directory '{p_output}' does not exist and could not be created: {e}", err=True)
            return

    click.echo(f"Processing '{p_filepath.name}', output at: '{p_output}'", err=True)
    
    grammar_contents = p_grammar.read_text(encoding="utf-8")

    with sqlite3.connect(p_db) as conn:
        configure_sqlite(conn)

        _verify_required_tables(conn)
        _load_colors_table(conn)

        start_time = time.perf_counter()

        files = [fp.as_posix() for fp in iter_ldraw_files([filepath])]
        
        try:
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_init_worker,
                initargs=(grammar_contents, str(p_db)),
            ) as executor:
                futures = {executor.submit(_process_file, fp): fp for fp in files}
                for future in as_completed(futures):
                    p_model, ann_model_contents, err = future.result()
                    if err:
                        click.echo(f"Error processing '{p_model.name}': {err}", err=True)
                        continue
                    
                    orig_ext = p_model.suffix.lower()

                    ann_ext = f".ann{orig_ext}"
                    p_ann_model = Path(output) / (p_model.stem + ann_ext)
                    p_ann_model.write_text(ann_model_contents or "", encoding="utf-8")

                    if verbose:
                        click.echo(f"Done annotating model: '{p_model.name}'.", err=True)

        except PermissionError:
            annotator = LDrawAnnotator(
                grammar_contents=grammar_contents,
                conn=conn,
            )
            for fp in files:
                p_fp = Path(fp)
                try:
                    ann_model_contents = annotator.process(p_fp)
                    orig_ext = p_fp.suffix.lower()
                    if orig_ext in {".ldr", ".dat", ".mpd"}:
                        ann_ext = f".ann{orig_ext}"
                        p_ann_model = Path(output) / (p_fp.stem + ann_ext)
                        p_ann_model.write_text(ann_model_contents, encoding="utf-8")
                    if verbose:
                        click.echo(f"Done annotating model: '{p_fp.name}'.", err=True)
                except Exception as e:
                    click.echo(f"Error processing {p_fp.name}: {e}", err=True)

        elapsed_time = time.perf_counter() - start_time

        click.echo(f"Finished processing. Time taken: {elapsed_time:.2f} seconds.", err=True)

if __name__ == "__main__":
    main()
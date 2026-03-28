#!/usr/bin/env python
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import files
from pathlib import Path
from typing import DefaultDict, Iterable
from unittest import result

import click
import pathvalidate
import subprocess
# from pydos2unix import dos2unix as d2u
# from dos2unix import 


LDRAW_EXTS = {".ldr", ".dat", ".mpd"}


def sanitize_filename(name: str) -> str:
    name = pathvalidate.sanitize_filename(name, platform="POSIX").lower()
    return pathvalidate.replace_symbol(
        name,
        "_",
        exclude_symbols=["."],
        is_replace_consecutive_chars=True,
        is_strip=True,
    )


def sanitize_filepath(fp: str) -> str:
    # normalize to POSIX-ish path + sanitize only the filename part (as original code did)
    sanitized = pathvalidate.sanitize_filepath(fp, platform="POSIX")
    p = Path(sanitized)
    return str(p.with_name(sanitize_filename(p.name)))


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


def sanitize_line_ref(line: str, ref_start_idx: int) -> str:
    tokens = line.split()
    if len(tokens) <= ref_start_idx:
        return line  # unexpected format; keep as-is

    ref = " ".join(tokens[ref_start_idx:])
    return " ".join(tokens[:ref_start_idx] + [sanitize_filepath(ref)])


# Global variable to avoid issues with lru_cache trying to cache defaultdict (unhashable) if we put it as an instance variable. 
# This is a bit hacky but keeps the caching working.
BASENAME_IDX: DefaultDict[str, list[str]] = defaultdict(list)

@dataclass(frozen=True)
class LDrawSanitizer:
    ldraw_dir: Path
    # _basename_index: DefaultDict[str, list[str]]

    @classmethod
    def from_ldraw_dir(cls, ldraw_dir: str | Path) -> "LDrawSanitizer":
        root = Path(ldraw_dir).resolve()
        idx: DefaultDict[str, list[str]] = defaultdict(list)

        for f in root.rglob("*"):
            if f.is_file():
                idx[f.name.lower()].append(str(f.relative_to(root)))

        global BASENAME_IDX
        BASENAME_IDX = idx  # store globally for alt_ref access

        return cls(ldraw_dir=root)

    @lru_cache(maxsize=200_000)
    def alt_ref(self, ref: str) -> str:
        """Return a valid alternative ref if possible, otherwise original ref.
        Also tries adding .dat if missing.
        """
        # Direct existence checks in common LDraw folders
        if (self.ldraw_dir / "p" / ref).exists() or (self.ldraw_dir / "parts" / ref).exists():
            return ref

        if not ref.lower().endswith(".dat"):
            return self.alt_ref(ref + ".dat")

        base = Path(ref).name.lower()
        alts = BASENAME_IDX.get(base, [])

        # Only rewrite when unambiguous
        return alts[0] if len(alts) == 1 else ref

    def fix_type1_refs_in_place(self, lines: list[str]) -> None:
        meta_refs = {line.split()[-1] for line in lines if line.startswith("0 FILE ")}

        for i, line in enumerate(lines):
            if not line.startswith("1 "):
                continue

            tokens = line.split()
            if not tokens:
                continue

            ref = tokens[-1]
            if ref in meta_refs:  # internal refs inside same MPD
                continue

            tokens[-1] = self.alt_ref(ref)
            lines[i] = " ".join(tokens)

    def type1_coords(self, lines: list[str]) -> dict[int, tuple[float, float, float]]:
        coords = {}

        for line_num, line in enumerate(lines):
            if not line.startswith("1 "):
                continue
            
            tokens = line.split()

            try:
                x, y, z = map(float, tokens[2:5])
                coords[line_num] = (x, y, z)
            except ValueError:
                click.echo(f"Warning: Could not parse coordinates in type1 line {line_num + 1}: {line}", err=True)

        return coords
    
    def canonicalize_coords(self, coords: dict[int, tuple[float, float, float]]) -> dict[int, tuple[int, int, int]]:

        # Find the piece closest to the origin: get the line number and the coordinates that satisfy that coords (item[1]) 
        # are the closest to (0,0,0), i.e. minimum modulus, but without the sqrt for efficiency since we only care about relative distances.
        m_line_num, (mx, my, mz) = min(coords.items(), key=lambda item: sum(c**2 for c in item[1]))

        click.echo(f"Closest piece to origin is on line {m_line_num + 1} with coordinates ({mx}, {my}, {mz})")

        # Translate all coordinates so that the closest piece is at the origin
        translated = {line_num: (x - mx, y - my, z - mz) for line_num, (x, y, z) in coords.items()}

        # Round coordinates to remove decimal noise
        rounded = {line_num: (round(x), round(y), round(z)) for line_num, (x, y, z) in translated.items()}

        return rounded
    
    def fix_type1_coords_in_place(self, lines: list[str], coords: dict[int, tuple[int, int, int]]) -> None:
        for line_num, (x, y, z) in coords.items():
            tokens = lines[line_num].split()
            tokens[2:5] = map(str, (x, y, z))
            lines[line_num] = " ".join(tokens)

    def process_file_coords(self, file: Path) -> None:
        click.echo(f"Processing coordinates in: {file.name}")

        lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        type1_coords = self.type1_coords(lines)

        canonical_coords = self.canonicalize_coords(type1_coords)

        self.fix_type1_coords_in_place(lines, canonical_coords)

        file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def type1_rots(self, lines: list[str]) -> dict[int, tuple[float, ...]]:
        rots = {}

        for line_num, line in enumerate(lines):
            if not line.startswith("1 "):
                continue
            
            tokens = line.split()

            try:
                line_rots = tuple(map(float, tokens[5:14]))
                rots[line_num] = line_rots
            except ValueError:
                click.echo(f"Warning: Could not parse rotation matrix in type1 line {line_num + 1}: {line}", err=True)

        return rots
    
    def canonicalize_rots(self, rots: dict[int, tuple[float, ...]]) -> dict[int, tuple[float, ...]]:

        # For now we will just round the rotation matrix values to remove decimal noise.
        # We could do this with "{0:.3g}".format alone, but keep this numeric approach for 
        # potential future enhancements like e.g. rotating the whole model to align to a canonical orientation
        rounded = {line_num: tuple(round(r, 2) for r in rs) for line_num, rs in rots.items()}

        return rounded
    
    def fix_type1_rots_in_place(self, lines: list[str], rots: dict[int, tuple[float, ...]]) -> None:
        for line_num, rs in rots.items():
            tokens = lines[line_num].split()
            # Remove as less decimal places as possible while keeping the same value, 2 decimal places at most 
            # i.e. 1.0 -> 1, 0.5000 -> 0.5, 0.3333333 -> 0.33 and 0.6666667 -> 0.67
            tokens[5:14] = map("{0:.3g}".format, rs)
            lines[line_num] = " ".join(tokens)

    def process_file_rots(self, file: Path) -> None:
        click.echo(f"Processing rotation matrixes in: {file.name}")

        lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        type1_rots = self.type1_rots(lines)

        canonical_rots = self.canonicalize_rots(type1_rots)

        self.fix_type1_rots_in_place(lines, canonical_rots)

        file.write_text("\n".join(lines) + "\n", encoding="utf-8")


    def process_file_references(self, file: Path) -> None:
        click.echo(f"Processing file references in: {file.name}")

        lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        out: list[str] = []

        for line in lines:
            line = line.strip()
            if line.startswith("0 FILE "):
                out.append(sanitize_line_ref(line, 2))
            elif line.startswith("1 "):
                out.append(sanitize_line_ref(line, 14))
            else:
                out.append(line)

        self.fix_type1_refs_in_place(out)
        file.write_text("\n".join(out) + "\n", encoding="utf-8")

    def process_filename(self, file: Path) -> None:
        new_name = sanitize_filename(file.name)
        if new_name == file.name:
            click.echo(f"Filename already sanitized: {file.name}")
            return

        dst = file.with_name(new_name)
        click.echo(f"Renaming {file.name} -> {dst.name}")
        file.rename(dst)

    def dos2unix_batch(self, fps: list[Path]) -> None:
        for f in fps:
            click.echo(f"Converting {f.name} from DOS to Unix format")

        # dos2unix can take multiple files
        cmd = ['dos2unix'] + [str(f) for f in fps]
    
        res = subprocess.run(cmd, capture_output=True, text=True)
    
        if res.returncode == 0:
            print(f"Converted {len(fps)} files")
        else:
            print(f"Error: {res.stderr}")


def _env_ldraw_dir() -> str | None:
    return Path(
        (Path.cwd() / "")  # harmless; just ensures Path exists in locals for type checkers
    ).__class__(  # type: ignore[attr-defined]
        ""  # dummy, overwritten below
    )  # not executed meaningfully


def env_ldraw_dir() -> str | None:
    # separated to keep it dead-simple and explicit
    import os

    return os.getenv("LDRAWDIR") or os.getenv("LDRAW_DIR")


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--file-references",
    type=click.Path(file_okay=True, dir_okay=True, readable=True, writable=True, exists=True, resolve_path=True),
    help="DEPRECATED: Inline edit FILE or files under DIR and type-1 lines: normalize paths, lowercase, remove spaces/symbols, and fix missing/ambiguous refs.",
)
@click.option(
    "--filepath",
    type=click.Path(file_okay=True, dir_okay=True, readable=True, writable=True, exists=True, resolve_path=True),
    help="Rename matching LDraw FILE or files under DIR to sanitized filenames (lowercase, no spaces, etc.).",
)
@click.option(
    "--coords",
    type=click.Path(file_okay=True, dir_okay=True, readable=True, writable=True, exists=True, resolve_path=True),
    help="Cleanup coordinates in type-1 lines on FILE or files under DIR: remove as much decimal noise as possible and translate origin to the piece closest to (0,0,0)",
)
@click.option(
    "--rots",
    type=click.Path(file_okay=True, dir_okay=True, readable=True, writable=True, exists=True, resolve_path=True),
    help="Cleanup rotation matrix in type-1 lines on FILE or files under DIR: remove as much decimal noise as possible",
)
@click.option(
    "--ldraw-dir",
    type=click.Path(file_okay=False, dir_okay=True, readable=True, exists=True, resolve_path=True),
    default=env_ldraw_dir(),
    help="Path to LDraw library root. Defaults to env LDRAWDIR or LDRAW_DIR.",
    required=True,
)
@click.option(
    "--dos2unix",
    type=click.Path(file_okay=True, dir_okay=True, readable=True, exists=True, resolve_path=True),
    help="Convert the given file from DOS to Unix, and also fix some UTF-8 encoding issues.",
)
def main(file_references: str | None, filepath: str | None, coords: str | None, rots: str | None, ldraw_dir: str | None, dos2unix: str | None) -> None:
    if not file_references and not filepath and not coords and not rots and not dos2unix:
        raise click.UsageError("Nothing to do. Provide one of: --file-references or --filepath or --coords or --rots.")

    sanitizer = None

    # TODO remove this, not a good idea, it will cause issues with "Windows-style" paths and dependencies
    # if file_references:
    #     if not ldraw_dir:
    #         raise click.UsageError("--ldraw-dir is required for --file-references (or set LDRAWDIR/LDRAW_DIR).")
    #     sanitizer = LDrawSanitizer.from_ldraw_dir(ldraw_dir)

    #     for fp in iter_ldraw_files([file_references]):
    #         try:
    #             sanitizer.process_file_references(fp)
    #         except Exception as e:
    #             click.echo(f"Error processing {fp}: {e}", err=True)
    #     return # skip other processing


    # sanitizer with a dummy root: the following don't require the full LDraw library
    sanitizer = LDrawSanitizer(ldraw_dir=Path("."))

    if coords:
        for fp in iter_ldraw_files([coords]):
            try:
                sanitizer.process_file_coords(fp)
            except Exception as e:
                click.echo(f"Error processing coordinates in {fp}: {e}", err=True)
                
        return

    if rots:
        for fp in iter_ldraw_files([rots]):
            try:
                sanitizer.process_file_rots(fp)
            except Exception as e:
                click.echo(f"Error processing rotation matrix in {fp}: {e}", err=True)

        return

    if filepath:
        for fp in iter_ldraw_files([filepath]):
            try:
                sanitizer.process_filename(fp)
            except Exception as e:
                click.echo(f"Error renaming {fp}: {e}", err=True)

        return

    if dos2unix:
        fps = []

        for fp in iter_ldraw_files([dos2unix]):
            fps.append(fp)
            if len(fps) > 10:
                sanitizer.dos2unix_batch(fps)
                fps = []
        if fps:
            sanitizer.dos2unix_batch(fps)

        return


if __name__ == "__main__":
    main()

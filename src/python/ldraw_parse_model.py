#!/usr/bin/env python
from enum import Enum

from ldraw_parser import parse_model_semantic
from pathlib import Path
import click
import shlex

ORIENTATIONS = {
    'yaw': {
        0: 'front-facing',
        45: 'front-right-facing',
        -45: 'front-left-facing',
        90: 'right-facing',
        -90: 'left-facing',
        135: 'rear-right-facing',
        -135: 'rear-left-facing',
        180: 'rear-facing',
        -180: 'rear-facing',
        225: 'rear-left-facing',
        -225: 'rear-right-facing',
    },
    'pitch': {
        0: 'upward-facing',
        45: 'upward-forward-facing',
        -45: 'upward-rearward-facing',
        90: 'forward-facing',
        -90: 'rearward-facing',
        135: 'downward-forward-facing',
        -135: 'downward-rearward-facing',
        180: 'downward-facing',
        -180: 'downward-facing',
        225: 'downward-rearward-facing',
        -225: 'downward-forward-facing',
    },
    'roll': {
        0: 'upright',
        45: 'slight-right-tilted',
        -45: 'slight-left-tilted',
        90: 'right-tilted',
        -90: 'left-tilted',
        135: 'steep-right-tilted',
        -135: 'steep-left-tilted',
        180: 'inverted',
        -180: 'inverted',
        225: 'steep-left-tilted',
        -225: 'steep-right-tilted',
    }
}

# 0: Comment or META Command
# 1: Sub-file reference
# 2: Line
# 3: Triangle
# 4: Quadrilateral
# 5: Optional Line
# enum LineType
class LineType(Enum):
    META = 0
    FILE_REF = 1
    LINE = 2
    TRIANGLE = 3
    QUADRILATERAL = 4
    OPTIONAL_LINE = 5  # also called: conditional line

    def __str__(self):
        return str(self.value)


def p_str(point: list[float]) -> str:
    return " ".join(f"{x:.10g}" for x in point)

def mat_str(matrix: list[list[float]]) -> str:
    return " ".join(f"{x:.10g}" for row in matrix for x in row)

class SubFileLine:
    lineType: LineType

class ColoredFileLine(SubFileLine):
    color: str


class Meta(SubFileLine):
    lineType: LineType = LineType.META
    contents: str

    def __init__(self, contents: str):
        self.contents = contents.strip()

    def __str__(self):
        return f"{self.lineType} {self.contents}"

class BangMeta(Meta):
    metaTag: str

    def __init__(self, contents: str):
        tokens = contents.split(" ", 1)
        self.contents = tokens[1] if len(tokens) > 1 else ""
        self.metaTag = tokens[0] if tokens else ""

    def __str__(self):
        return f"{self.lineType} {self.metaTag} {self.contents}"

class File(Meta):
    name: str

    def __init__(self, name: str):
        self.name = name.strip()
        super().__init__(contents=name.strip())

    def __str__(self):
        return f"{self.lineType} FILE {self.name}"


class Description(Meta):
    pass


class Name(Meta):
    def __str__(self):
        return f"{self.lineType} Name: {self.contents}"


class Step(Meta):
    count: int = -1

    def __init__(self, semStep: dict):
        self.count = semStep["step"]
    
    def __str__(self):
        # steps don't get numbers, we got those from parsing
        return f"\n{self.lineType} STEP\n"


class Line(ColoredFileLine):
    lineType: LineType = LineType.LINE
    p1: list[float]
    p2: list[float]

    def __init__(self, semLine: dict):
        sl = semLine["line"]

        self.color = sl["color"]
        self.p1 = sl["p1"]
        self.p2 = sl["p2"]

    def __str__(self):
        return f"{self.lineType} {self.color} {p_str(self.p1)} {p_str(self.p2)}"


class Triangle(ColoredFileLine):
    lineType: LineType = LineType.TRIANGLE

    p1: list[float]
    p2: list[float]
    p3: list[float]

    def __init__(self, semTriangle: dict):
        st = semTriangle["triangle"]

        self.color = st["color"]
        self.p1 = st["p1"]
        self.p2 = st["p2"]
        self.p3 = st["p3"]

    def __str__(self):
        return f"{self.lineType} {self.color} {p_str(self.p1)} {p_str(self.p2)} {p_str(self.p3)}"


class Quadrilateral(ColoredFileLine):
    lineType: LineType = LineType.QUADRILATERAL

    p1: list[float]
    p2: list[float]
    p3: list[float]
    p4: list[float]

    def __init__(self, semQuad: dict):
        sq = semQuad["quad"]

        self.color = sq["color"]
        self.p1 = sq["p1"]
        self.p2 = sq["p2"]
        self.p3 = sq["p3"]
        self.p4 = sq["p4"]

    def __str__(self):
        return f"{self.lineType} {self.color} {p_str(self.p1)} {p_str(self.p2)} {p_str(self.p3)} {p_str(self.p4)}"

class OptionalLine(SubFileLine):
    lineType: LineType = LineType.OPTIONAL_LINE

    color: str = ""
    p1: list[float] 
    p2: list[float] 
    p3: list[float] 
    p4: list[float]

    def __init__(self, semOptionalLine: dict):
        sol = semOptionalLine["cond"]

        self.color = sol["color"]
        self.p1 = sol["p1"]
        self.p2 = sol["p2"]
        self.p3 = sol["p3"]
        self.p4 = sol["p4"]

    def __str__(self):
        return f"{self.lineType} {self.color} {p_str(self.p1)} {p_str(self.p2)} {p_str(self.p3)} {p_str(self.p4)}"


class Keywords(BangMeta):
    keywords: list[str]
    rebrickableId: str | None = None
    bricklinkId: str | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.keywords = self.contents.split(",")
        # maybe rebrickable or bricklink id are in the keywords
        for kw in self.keywords:
            kw = kw.strip()
            kwup = kw.upper()
            if kwup.startswith("REBRICKABLE"):
                self.rebrickableId = kw.split(" ", 1)[1].strip() if " " in kw else None
                break
            elif kwup.startswith("BRICKLINK"):
                self.bricklinkId = kw.split(" ", 1)[1].strip() if " " in kw else None
                break

    def hasKeyword(self, keyword: str) -> bool:
        return any(kw.strip().upper() == keyword.strip().upper() for kw in self.keywords)


class Theme(BangMeta):
    pass


class Category(BangMeta):
    pass


class PartInfoMeta(BangMeta):
    # example: 0 !P P3 'Car Base  4 x  5' 'Yellow' front-facing,upward-facing,upright 80x20x100 LDU
    pid: str = ""
    description: str = ""
    colorName: str = ""
    dimensions: str = ""
    orientation: str = ""

    def __init__(self, contents: str | None = None, **kwargs):

        # either we can initialize with the full contents of the meta command, or with specific fields, but not both
        if contents is not None:
            super().__init__(contents=contents)
            tokens = shlex.split(self.contents)

            self.pid = tokens[0] if len(tokens) > 0 else "(unknown)"
            self.description = tokens[1] if len(tokens) > 1 else "(no description)"
            self.colorName = tokens[2] if len(tokens) > 2 else "(no color)"
            self.orientation = tokens[3] if len(tokens) > 3 else "(no orientation)"
            self.dimensions = tokens[4] if len(tokens) > 4 else "(no dimensions)"
        else:
            super().__init__(contents="")
            self.pid = kwargs.get("pid", "(unknown)")
            self.description = kwargs.get("description", "(no description)")
            self.colorName = kwargs.get("colorName", "(no color)")
            self.orientation = kwargs.get("orientation", "(no orientation)")
            self.dimensions = kwargs.get("dimensions", "(no dimensions)")

    def __str__(self):
        return f"\n{self.lineType} !P {self.pid} '{self.description}' '{self.colorName}' {self.orientation} {self.dimensions} LDU"

class PartTouchesMeta(BangMeta):
    # example: 0 !TOUCHES ⚠️P2@bottom-left P4@top-right P5@right P6@left P7@bottom ⚠️P8@top P9@bottom-right P10@bottom
    pids: list[str]
    intersects: set[str]  # set of pids that intersect (e.g. {"P2", "P8"})
    relPositions: dict[str, str]  # pid -> relative position (e.g. "P2" -> "BL")

    def __init__(self, contents: str | None = None, **kwargs):
        
        if contents is not None:
            super().__init__(contents=contents)
            tokens = shlex.split(self.contents)

            self.pids = []
            self.intersects = set()
            self.relPositions = {}

            for t in tokens:
                st = t.split("@")
                pid = st[0]

                if pid.startswith("⚠️"):
                    pid = pid.removeprefix("⚠️")
                    self.intersects.add(pid)
                
                self.relPositions[pid] = st[1]
                self.pids.append(pid)
        else:
            super().__init__(contents="")
            self.pids = kwargs.get("pids", [])
            self.intersects = kwargs.get("intersects", set())
            self.relPositions = kwargs.get("relPositions", {})

    def __str__(self):
        items = []

        for pid in self.pids:
            rel_pos = self.relPositions[pid]
            warn = "⚠️" if pid in self.intersects else ""
            item = f"{warn}{pid}@{rel_pos}"
            
            items.append(item)

        pids_str = " ".join(items)

        return f"{self.lineType} !TOUCHES {pids_str}"

class FileRef(SubFileLine):
    lineType: LineType = LineType.FILE_REF
    globalOrdinal: int
    ordinal: int
    ref: str
    color: str
    position: list[float]
    matrix: list[list[float]]
    rotation: list[float]
    

    def __init__(self, semFileRef: dict, ordinal: int):
        self.ordinal = ordinal
        spr = semFileRef["part"]

        self.color = spr["color"]
        self.position = spr["position"]
        self.matrix = spr["matrix"]
        self.rotation = spr["rotation"]
        self.ref = spr["file_ref"].strip()

    def __str__(self):
        return f"{self.lineType} {self.color} {p_str(self.position)} {mat_str(self.matrix)} {self.ref}"


class SubFileLinesGroup:
    subFileLines: list[SubFileLine]

    def __init__(self):
        self.subFileLines = []


class SubFileHeader(SubFileLinesGroup):
    file: File 
    description: Description
    name: Name
    author: Meta
    keywords: Keywords
    category: Category
    theme: Theme

    def __init__(self, semHeader: dict):
        super().__init__()
        self.file = None
        self.description = None
        self.name = None
        self.author = None
        self.keywords = None
        self.category = None
        self.theme = None
        for sl in semHeader["header"]:
            # every sl is actually a meta dict with just one k,v, get k and v
            key, value = list(sl.items())[0]

            m: Meta = None

            if key == "file":
                self.file = File(name=value.strip())  # remove quotes around file name
                m = self.file
            elif key == "description":
                self.description = Description(contents=value)
                m = self.description
            elif key == "name":
                self.name = Name(contents=value)
                m = self.name
            elif key == "author":
                # FIXME author, license, etc. meta commands require specific classes and/or handling
                self.author = Meta(contents=value)
                m = self.author
            elif key == "meta":
                m = self._selectMeta(value)

            # FIXME sometimes, STEPs are parsed and included as part of the header, even when they are not
            # we will ignore them for now, but we should find a better way to distinguish them from actual header meta commands
            if m is not None:
                self.subFileLines.append(m)

        # make a best effort: not all the models are standard compliant, so we try to fill with what we have
        if self.name is None:
            self.name = Name(contents=self.file.name if self.file 
                             else self.description.contents if self.description 
                             else "(unknown)")
            
        if self.description is None:
            self.description = Description(contents=self.name.contents if self.name 
                                           else self.file.name if self.file 
                                           else "(unknown)")

        if self.file is None:
            # this could happen, either due to some error or because we are actually dealing with a .ldr or .dat file
            self.file = File(name="__root__")
            self.subFileLines.insert(0, self.file)  # ensure file meta is the first line of the header

    def _selectMeta(self, metaContents: str) -> Meta:
        if metaContents.startswith("!KEYWORDS "):
            return Keywords(contents=metaContents)
        elif metaContents.startswith("!CATEGORY "):
            return Category(contents=metaContents)
        elif metaContents.startswith("!THEME "):
            return Theme(contents=metaContents)
        else:
            return Meta(contents=metaContents)
        
    def __str__(self):
        return "\n".join(str(ml) for ml in self.subFileLines)

class PartRef:
    fileRef: FileRef
    partInfoMeta: PartInfoMeta
    partTouchesMeta: PartTouchesMeta
    orientation: list[str]
    internal: bool = False  # whether the partRef is a reference to an embedded submodel/subfile (True) or external submodel or part (False)

    def __init__(self, fileRef: FileRef):
        self.fileRef = fileRef

        def approx_angle(angle: float) -> int:
            """Approximate angle to nearest 45° increment."""
            return round(angle / 45) * 45

        yaw, pitch, roll = [approx_angle(angle) for angle in self.fileRef.rotation]

        self.orientation = [
            ORIENTATIONS['yaw'][yaw],
            ORIENTATIONS['pitch'][pitch],
            ORIENTATIONS['roll'][roll]
        ]

class SubFile(SubFileLinesGroup):
    ordinal: int
    header: SubFileHeader

    def __init__(self, semSubfile: dict, ordinal: int):
        super().__init__()
        self.ordinal = ordinal
        semHeader = semSubfile["subfile"][0]
        semBody = semSubfile["subfile"][1]

        self.header = SubFileHeader(semHeader)

        fr_counter = 0

        for sl in semBody["body"]:
            if "part" in sl:
                fr_counter += 1
                self.subFileLines.append(FileRef(sl, fr_counter))
            elif "line" in sl:
                self.subFileLines.append(Line(sl))
            elif "triangle" in sl:
                self.subFileLines.append(Triangle(sl))
            elif "quad" in sl:
                self.subFileLines.append(Quadrilateral(sl))
            elif "cond" in sl:
                self.subFileLines.append(OptionalLine(sl))
            elif "step" in sl:
                self.subFileLines.append(Step(sl))
            elif "meta" in sl:
                self.subFileLines.append(self._selectMeta(sl["meta"]))

    def _selectMeta(self, metaContents: str) -> Meta:
        if metaContents.startswith("!P "):
            return PartInfoMeta(contents=metaContents)
        elif metaContents.startswith("!TOUCHES "):
            return PartTouchesMeta(contents=metaContents)
        else:
            return Meta(contents=metaContents)
        
    def __str__(self):
        h_str = str(self.header) if self.header else ""
        b_str = "\n".join(str(ml) for ml in self.subFileLines)
        return f"{h_str}\n{b_str}"

class SubModel:
    fqn: str
    subFile : SubFile
    partRefs: list[PartRef]
    numSteps: int
    numParts: int
    isAssembly: bool

    def __init__(self, subFile: SubFile):
        self.subFile = subFile
        self.isAssembly = self._guessAssembly()

        # conceptually group the partRefs and submodelRefs, i.e. internal or external file references

        self.partRefs = []

        for i, sfl in enumerate(subFile.subFileLines):
            if isinstance(sfl, FileRef):
                fr: FileRef = sfl
                pr = PartRef(fileRef=fr)

                # if present, previous line(s) maybe a PartInfoMeta, a PartTouchesMeta or both related to this partRef
                prev_idxs = [i - 1, i - 2]
                prevs = [subFile.subFileLines[idx] for idx in prev_idxs if idx >= 0]

                for prev in prevs:
                    if isinstance(prev, PartInfoMeta):
                        pr.partInfoMeta = prev
                    if isinstance(prev, PartTouchesMeta):
                        pr.partTouchesMeta = prev

                self.partRefs.append(pr)

        self.numParts = len(self.partRefs)

        self.numSteps = sum(1 for l in subFile.subFileLines if isinstance(l, Step))

    def _guessAssembly(self):
        h = self.subFile.header

        vals = [
            h.description.contents if h.description else "",
            h.name.contents if h.name else "",
            h.file.name if h.file else ""
        ]

        return any("assembly" in v.lower() for v in vals)

    def updateInternalRefs(self, internal_refs: list[str]):
        # refs many times are Windows-style case-insensitive, so we will compare them in a case-insensitive way
        win_internal_refs = set(ref.upper() for ref in internal_refs)

        for pr in self.partRefs:
            ref = pr.fileRef.ref
            pr.internal = ref.upper() in win_internal_refs

    def __str__(self):
        return str(self.subFile)
    
class MPDModel:
    subModels: list[SubModel]
    mainModel: SubModel

    def __init__(self, semTree: dict):
        subFiles = [SubFile(semSubfile, ord) for ord, semSubfile in enumerate(semTree["model"])]
        self.subModels = [SubModel(subFile) for subFile in subFiles]

        # we know these are internal refs names because every 0 FILE meta command 
        # defines a new subfile, that should be referenced elsewhere in the same model file
        # so, given a subfile, it's name should appear on some fileRef.ref on the same model
        internal_refs = [sf.header.file.name for sf in subFiles]

        self.mainModel = self.subModels[0]
        mainFileName = self.mainModel.subFile.header.file.name

        # finish submodels by adding info not available before all submodels have been parsed
        for sm in self.subModels:
            subFileName = sm.subFile.header.file.name
            # this fqn will be required elsewhere, in order to properly identify submodels thanks to their path + fqn
            prefix = f"{mainFileName} | " if sm != self.mainModel else ""
            sm.fqn = f"{prefix}{subFileName}"

            sm.updateInternalRefs(internal_refs)

        all_file_refs = [pr.fileRef for sm in self.subModels for pr in sm.partRefs]

        # the order will be the same as the natural order in the submodels, file refs, etc.
        for i, fr in enumerate(all_file_refs):
            fr.globalOrdinal = i + 1

    def setPartInfoMeta(self, partRef: PartRef, partInfoMeta: PartInfoMeta, subModel: SubModel):
        # We need to update the fileLines to include it
        fileRef = partRef.fileRef
        subFileLines = subModel.subFile.subFileLines

        fileRefIdx = subFileLines.index(fileRef)

        # Insert the partInfoMeta right before the fileRef in the subFileLines
        subFileLines.insert(fileRefIdx, partInfoMeta)

        # Update the partRef to include the new partInfoMeta
        partRef.partInfoMeta = partInfoMeta

    def setPartTouchesMeta(self, partRef: PartRef, partTouchesMeta: PartTouchesMeta, subModel: SubModel):
        # We need to update the fileLines to include it
        fileRef = partRef.fileRef
        subFileLines = subModel.subFile.subFileLines

        fileRefIdx = subFileLines.index(fileRef)

        # Insert the partTouchesMeta right before the fileRef in the subFileLines
        subFileLines.insert(fileRefIdx, partTouchesMeta)

        # Update the partRef to include the new partTouchesMeta
        partRef.partTouchesMeta = partTouchesMeta

        
    def __str__(self):
        return "\n\n".join(str(sm) for sm in self.subModels)


@click.command()
@click.option(
    "-g", "--grammar",
    type=click.Path(file_okay=True, dir_okay=False, readable=True, writable=False, exists=True, resolve_path=True),
    help="Get lark grammar for semantic parsing a model. If not provided it uses the one on LDRAW_GRAMMAR env variable.",
    envvar="LDRAW_GRAMMAR",
    required=True,
)
@click.option(
    "-m", "--model", type=click.Path(file_okay=True, dir_okay=False, readable=True, writable=False, exists=True, resolve_path=True),
    help="LDraw model file to parse: .ldr, .mpd, .dat", required=True
)
def parse(grammar, model):
    # TODO this only proves roundtrip parsing, to be sure that parsing into a model and then printing it back to ldraw format is correct
    p_grammar = Path(grammar)
    p_model = Path(model)
    
    grammar_str = p_grammar.read_text(encoding="utf-8")
    model_str = p_model.read_text(encoding="utf-8")

    semTree = parse_model_semantic(model_str, grammar_str)

    mpdModel = MPDModel(semTree)

    for sm in mpdModel.subModels:
        print(sm)

if __name__ == "__main__":
    parse()


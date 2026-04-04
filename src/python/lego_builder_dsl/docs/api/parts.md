<!-- markdownlint-disable -->

<a href="../../../../../src/python/lego_builder_dsl/lego_builder/parts.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `parts`
Part catalog: PartType enum, Part definitions, Color constants, and lookup. 

This module contains the complete catalog of available LEGO parts and the greedy fill order used by wall/roof tiling algorithms. 

**Global Variables**
---------------
- **PARTS**
- **FILL_BRICKS**

---

<a href="../../../../../src/python/lego_builder_dsl/lego_builder/parts.py#L138"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `find_part`

```python
find_part(
    part_type: 'PartType',
    description: 'str' = '',
    color: 'str' = ''
) → Part
```

Look up a part by its PartType enum value. 

Current implementation: exact match on part_type, ignores description/color. Future (RAG): description and color will be used for semantic search within the matched part_type category. 



**Args:**
 
 - <b>`part_type`</b>:  Exact part identifier (required). 
 - <b>`description`</b>:  Semantic description for future RAG filtering. 
 - <b>`color`</b>:  Semantic color hint for future RAG filtering. 



**Returns:**
 The matching Part definition. 



**Raises:**
 
 - <b>`BuilderError`</b>:  If part_type is not found in catalog. 


---

<a href="../../../../../src/python/lego_builder_dsl/lego_builder/parts.py#L25"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `PartType`
Enumeration of available LEGO parts. 

Naming convention:  BRICK_DxW     — standard brick, D studs deep, W studs wide  PLATE_DxW     — standard plate, D studs deep, W studs wide  WINDOW_DxWxH  — window (complete), D deep, W wide, H high (in bricks)  DOOR_DxWxH    — door frame, D deep, W wide, H high (in bricks)  SLOPE_DxW     — 45° slope brick 





---

<a href="../../../../../src/python/lego_builder_dsl/lego_builder/parts.py#L65"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `Part`
A LEGO part definition with its LDraw filename and dimensions. 

Dimensions are in internal units:  width_studs  — along the part's local X axis (in studs)  depth_studs  — along the part's local Z axis (in studs)  height_plates — along Y axis (in plates: brick=3, plate=1) 

<a href="../../../../../src/python/lego_builder_dsl/<string>"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(
    filename: 'str',
    description: 'str',
    width_studs: 'int',
    depth_studs: 'int',
    height_plates: 'int'
) → None
```









---

<a href="../../../../../src/python/lego_builder_dsl/lego_builder/parts.py#L175"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `Color`
Common LDraw color codes as named constants. 

Usage: Color.RED, Color.WHITE, etc. The LLM can also use raw integers if needed. 







---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._

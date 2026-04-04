<!-- markdownlint-disable -->

<a href="../../../../../src/python/lego_builder_dsl/lego_builder/coords.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `coords`
Coordinate system constants and conversions for the LDraw builder. 

MENTAL MODEL (read this first): 
  - Internally we use stud units (X, Z horizontal) and plate units (Y vertical). 
  - Y is positive-up in our system. 
  - LDraw's Y axis is INVERTED: negative Y = upward, positive Y = downward. 
  - Conversion to LDraw coordinates happens ONLY at export time. 
  - Part origins in LDraw sit at the TOP of the brick body (where studs connect).  The body extends DOWNWARD (positive Y in LDraw).  Studs extend UPWARD (negative Y in LDraw) by ~4 LDU. 

Unit conversions: 
  - 1 stud  = 20 LDU  (horizontal, X and Z axes) 
  - 1 plate =  8 LDU  (vertical, Y axis) 
  - 1 brick =  3 plates = 24 LDU 

Stacking: 
  - Brick at row N has y_plates = N * 3. 
  - In LDraw coords: ly = -(N * 3) * 8 = -N * 24. 
  - Row 0: ly = 0. Row 1: ly = -24. Row 2: ly = -48. Etc. 

**Global Variables**
---------------
- **LDU_PER_STUD**
- **LDU_PER_PLATE**
- **PLATES_PER_BRICK**
- **ROTATION_MATRICES**
- **FACING_TO_ROTATION**

---

<a href="../../../../../src/python/lego_builder_dsl/lego_builder/coords.py#L36"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `to_ldraw_coords`

```python
to_ldraw_coords(
    x_studs: 'float',
    y_plates: 'float',
    z_studs: 'float'
) → tuple[float, float, float]
```

Convert internal (stud, plate, stud) coords to LDraw (LDU, LDU, LDU). 

LDraw Y axis is inverted: negative = up. Our y_plates is positive-up, so we negate when converting. 




---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._

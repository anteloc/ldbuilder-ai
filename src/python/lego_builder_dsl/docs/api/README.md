<!-- markdownlint-disable -->

# API Overview

## Modules

- [`coords`](./coords.md#module-coords): Coordinate system constants and conversions for the LDraw builder.
- [`parts`](./parts.md#module-parts): Part catalog: PartType enum, Part definitions, Color constants, and lookup.

## Classes

- [`parts.Color`](./parts.md#class-color): Common LDraw color codes as named constants.
- [`parts.Part`](./parts.md#class-part): A LEGO part definition with its LDraw filename and dimensions.
- [`parts.PartType`](./parts.md#class-parttype): Enumeration of available LEGO parts.

## Functions

- [`coords.to_ldraw_coords`](./coords.md#function-to_ldraw_coords): Convert internal (stud, plate, stud) coords to LDraw (LDU, LDU, LDU).
- [`parts.find_part`](./parts.md#function-find_part): Look up a part by its PartType enum value.


---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._

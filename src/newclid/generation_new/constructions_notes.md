# Construction Notes

This file preserves the explanatory comments and disabled entries that were present when the construction lists lived directly in `constructions.py`.

## Group Meanings

- `BASIC`: basic constructions that create the initial shape.
- `BASIC_FREE`: free-point construction.
- `INTERSECT`: intersection-based constructions that usually create points from lines or circles.
- `OTHER`: single-point or special constructions.

## Original Inline Notes

### `INTERSECT`

- `angle_bisector` => `bisect` => `LineNum`
- `angle_mirror` => `amirror` => `LineNum`
- `eqdistance` => `circle` => `CircleNum`
- `on_line` => `line` => `LineNum`
- `on_aline` => `aline` => `LineNum`
- `on_bline` => `bline` => `LineNum`
- `on_pline` => `pline` => `LineNum`
- `on_tline` => `tline` => `LineNum`
- `on_dia` => `dia` => `CircleNum`
- `on_circle` => `circle` => `CircleNum`
- `on_circum` => `cyclic` => `CircleNum`
- `eqratio` => `eqratio` => `CircleNum`
- `lc_tangent` => `tline` => `LineNum`

### `OTHER`

- Includes special constructions such as midpoint, reflection, orthocenter, tangents, and intersection helpers.

## Previously Disabled Entries

These entries were commented out in the old Python list definitions and are intentionally not active in `constructions.json`.

### `BASIC`

- `iso_triangle0`

### `INTERSECT`

- `on_aline0`
- `on_pline0`
- `eqangle3`
- `eqratio6`
- `rconst`
- `rconst2`
- `aconst`
- `s_angle`
- `lconst`

Original note:
- `rconst`: TODO double check whether this is needed

### `OTHER`

- `circumcenter`
- `eqangle2`
- `ninepoints`
- `nsquare`
- `psquare`
- `shift`
- `2l1c`
- `e5128`
- `3peq`
- `trisect`
- `trisegment`
- `iso_triangle_vertex`
- `iso_triangle_vertex_angle`

## Why This File Exists

- `constructions.json` is the runtime source of truth because it is easy to load, cache, and override in experiments.
- JSON does not support comments, so this file keeps the human-facing context that would otherwise be lost.
- When adjusting the default construction pools, update both `constructions.json` and this notes file if the rationale or disabled-entry list changes.

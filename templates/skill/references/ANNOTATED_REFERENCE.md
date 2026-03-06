# Orientation table

| Axis  | Degrees  | Orientation                    |
|-------|----------|--------------------------------|
| Yaw   | 0°       | front-facing                   |
| Yaw   | +45°     | front-right-facing             |
| Yaw   | -45°     | front-left-facing              |
| Yaw   | +90°     | right-facing                   |
| Yaw   | -90°     | left-facing                    |
| Yaw   | +135°    | rear-right-facing              |
| Yaw   | -135°    | rear-left-facing               |
| Yaw   | ±180°    | rear-facing                    |
| Yaw   | +225°    | rear-left-facing               |
| Yaw   | -225°    | rear-right-facing              |
| Pitch | 0°       | upward-facing                  |
| Pitch | +45°     | upward-forward-facing          |
| Pitch | -45°     | upward-rearward-facing         |
| Pitch | +90°     | forward-facing                 |
| Pitch | -90°     | rearward-facing                |
| Pitch | +135°    | downward-forward-facing        |
| Pitch | -135°    | downward-rearward-facing       |
| Pitch | ±180°    | downward-facing                |
| Pitch | +225°    | downward-rearward-facing       |
| Pitch | -225°    | downward-forward-facing        |
| Roll  | 0°       | upright                        |
| Roll  | +45°     | slight-right-tilted            |
| Roll  | -45°     | slight-left-tilted             |
| Roll  | +90°     | right-tilted                   |
| Roll  | -90°     | left-tilted                    |
| Roll  | +135°    | steep-right-tilted             |
| Roll  | -135°    | steep-left-tilted              |
| Roll  | ±180°    | inverted                       |
| Roll  | +225°    | steep-left-tilted              |
| Roll  | -225°    | steep-right-tilted             |

Also, combinations apply, like e.g.: front-facing,upward-facing,upright

# Intersection warnings

Indicated by the presence of ⚠️ symbol.

# Part metatag: !P

Tags and describes a piece on a file.

- Format: 
```
0 !P {pid} '{description}' '{color name}' {world-orientation} {WxHxL dimensions} LDU
```

- Example:
```
0 !P P4 'Brick  2 x  2' 'Pink' front-facing,upward-facing,upright 40x28x40 LDU
```

# Part contacts: !TOUCHES

- Format:
```
0 !TOUCHES {optional ⚠️}{pid_in_contact}@{relative-orientation} ...
```

# Example: !P and !TOUCHES

This is an example of an annotated type-1 line:

```
0 !P P4 'Brick  2 x  2' 'Pink' front-facing,upward-facing,upright 40x28x40 LDU
0 !TOUCHES P1@right ⚠️P2@top-right
1 13 -260 -28 -100 1 0 0 0 1 0 0 0 1 3003.dat
```

Which means:
- Part P4 is a 'Brick  2 x  2', in 'Pink' color, with world orientation front-facing,upward-facing,upright, and dimensions 40x28x40 LDU
- This part touches P1 to its right, and intersects with P2 at its top right


"""
sudoku.py
---------
The puzzle definition and grid helpers. The PUZZLE is the set of GIVEN
clues (0 = empty cell). Givens are never moved or mutated by the GA.

Two puzzles are provided; pick one via the PUZZLE env var ("easy"|"classic").
"""

import os

GRID = 9
BOX = 3

# A medium puzzle (the classic Wikipedia example, unique solution).
CLASSIC = [
    5, 3, 0, 0, 7, 0, 0, 0, 0,
    6, 0, 0, 1, 9, 5, 0, 0, 0,
    0, 9, 8, 0, 0, 0, 0, 6, 0,
    8, 0, 0, 0, 6, 0, 0, 0, 3,
    4, 0, 0, 8, 0, 3, 0, 0, 1,
    7, 0, 0, 0, 2, 0, 0, 0, 6,
    0, 6, 0, 0, 0, 0, 2, 8, 0,
    0, 0, 0, 4, 1, 9, 0, 0, 5,
    0, 0, 0, 0, 8, 0, 0, 7, 9,
]

# An easy puzzle (more givens -> GA solves it reliably; good for a clean demo).
EASY = [
    5, 3, 4, 6, 7, 8, 9, 1, 0,
    6, 7, 2, 1, 9, 5, 3, 4, 8,
    1, 9, 8, 3, 4, 2, 5, 6, 7,
    8, 5, 9, 7, 6, 1, 4, 2, 3,
    4, 2, 6, 8, 5, 3, 7, 9, 1,
    7, 1, 3, 9, 2, 4, 8, 5, 6,
    9, 6, 1, 5, 3, 7, 2, 8, 4,
    2, 8, 7, 4, 1, 9, 6, 3, 0,
    3, 4, 5, 2, 8, 6, 1, 7, 9,
]

# A genuinely solvable-by-GA medium puzzle with a fair number of givens.
MEDIUM = [
    0, 0, 0, 2, 6, 0, 7, 0, 1,
    6, 8, 0, 0, 7, 0, 0, 9, 0,
    1, 9, 0, 0, 0, 4, 5, 0, 0,
    8, 2, 0, 1, 0, 0, 0, 4, 0,
    0, 0, 4, 6, 0, 2, 9, 0, 0,
    0, 5, 0, 0, 0, 3, 0, 2, 8,
    0, 0, 9, 3, 0, 0, 0, 7, 4,
    0, 4, 0, 0, 5, 0, 0, 3, 6,
    7, 0, 3, 0, 1, 8, 0, 0, 0,
]

_PUZZLES = {"easy": EASY, "classic": CLASSIC, "medium": MEDIUM}


def get_puzzle():
    name = os.getenv("PUZZLE", "classic").lower()
    return _PUZZLES.get(name, CLASSIC), name


def given_mask(puzzle):
    """True where the cell is a fixed given clue."""
    return [v != 0 for v in puzzle]


def pretty(flat):
    """Return a printable 9x9 grid string."""
    lines = []
    for r in range(GRID):
        row = flat[r * GRID:(r + 1) * GRID]
        cells = []
        for c in range(GRID):
            cells.append(str(row[c]) if row[c] else ".")
            if c % BOX == BOX - 1 and c != GRID - 1:
                cells.append("|")
        lines.append(" ".join(cells))
        if r % BOX == BOX - 1 and r != GRID - 1:
            lines.append("-" * 21)
    return "\n".join(lines)

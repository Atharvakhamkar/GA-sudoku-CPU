"""
ga.py  (SUDOKU — COMPACT CHROMOSOME)
------------------------------------
Single-island GA using a COMPACT chromosome.

WHY COMPACT (the design decision):
  The old chromosome stored all 81 cells, including the fixed givens — the GA
  can never change a given, so storing them is wasted space. The genome should
  contain ONLY the decision variables: the digits the GA actually places.

REPRESENTATION:
  An individual is 9 short lists, one per row. Row r's list is an ARRANGEMENT
  of exactly the digits that are MISSING from that row (the givens are excluded).
  Length of row r's list = number of EMPTY cells in row r.
    e.g. a row "5 . 4 . 7 . 9 . ."  has givens {5,4,7,9} and missing {1,2,3,6,8},
    so its compact gene is a permutation of [1,2,3,6,8]  (5 numbers, not 9).
  Total chromosome size = (81 - number_of_givens), e.g. 45 for a 36-given puzzle
  instead of 81 — roughly 44% smaller.

INVARIANTS (free by construction):
  * Every row's gene is a permutation of that row's missing set -> rows always valid.
  * Givens are never stored, so they can never be corrupted.
  * Mutation/crossover touch only free cells automatically (no given-checking).

SCORING:
  expand() rebuilds the full 81-cell grid (givens + placed digits) right before
  sending to the fitness pool, so the WORKERS STAY UNCHANGED, identical, and
  stateless. A solved grid scores MAX_SCORE = 162.
"""

import random

GRID = 9


class SudokuGA:
    def __init__(self, puzzle, given_mask, pop_size, mutation_rate,
                 crossover_rate, tournament_k, elite_count,
                 hypermutation_factor=6, seed=None):
        self.puzzle = puzzle                # flat 81, givens in place, 0 = empty
        self.mask = given_mask
        self.pop_size = pop_size
        self.base_mutation_rate = mutation_rate
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.tournament_k = tournament_k
        self.elite_count = elite_count
        self.hypermutation_factor = hypermutation_factor
        self.rng = random.Random(seed)

        # Per row: which cell positions are free, and which digits are missing.
        # These depend ONLY on the puzzle, so they are shared by every individual.
        self.row_missing = []
        self.row_free_pos = []
        for r in range(GRID):
            row = puzzle[r * GRID:(r + 1) * GRID]
            present = {v for v in row if v != 0}
            missing = [d for d in range(1, 10) if d not in present]
            free = [c for c in range(GRID) if row[c] == 0]
            self.row_missing.append(missing)
            self.row_free_pos.append(free)

        # The compact chromosome length (for reporting the saving)
        self.chrom_length = sum(len(m) for m in self.row_missing)

        self.population = [self._random_individual() for _ in range(pop_size)]
        self.fitnesses = [0] * pop_size

    # ---- a COMPACT individual: 9 lists of missing-digit arrangements ----
    def _random_individual(self):
        ind = []
        for r in range(GRID):
            gene = self.row_missing[r][:]   # the digits to place in row r
            self.rng.shuffle(gene)
            ind.append(gene)
        return ind

    # ---- expand compact -> full flat 81 grid (givens + placed digits) ----
    def expand(self, individual):
        grid = self.puzzle[:]               # copy: givens in place, 0 in free cells
        for r in range(GRID):
            base = r * GRID
            for pos, digit in zip(self.row_free_pos[r], individual[r]):
                grid[base + pos] = digit
        return grid

    # ---- selection ----
    def tournament_selection(self):
        best = self.rng.randrange(self.pop_size)
        for _ in range(self.tournament_k - 1):
            ch = self.rng.randrange(self.pop_size)
            if self.fitnesses[ch] > self.fitnesses[best]:
                best = ch
        return self.population[best]

    # ---- crossover: swap whole compact rows ----
    # Both parents' row r are permutations of the SAME missing set, so swapping
    # entire rows always yields valid children.
    def crossover(self, p1, p2):
        if self.rng.random() > self.crossover_rate:
            return [g[:] for g in p1], [g[:] for g in p2]
        point = self.rng.randrange(1, GRID)
        c1 = [g[:] for g in p1[:point]] + [g[:] for g in p2[point:]]
        c2 = [g[:] for g in p2[:point]] + [g[:] for g in p1[point:]]
        return c1, c2

    # ---- mutation: swap two entries within a row's compact gene ----
    # Every entry is a free cell, so any swap keeps the gene a valid permutation.
    def mutate(self, individual):
        for r in range(GRID):
            gene = individual[r]
            if len(gene) < 2:
                continue
            if self.rng.random() < self.mutation_rate:
                a, b = self.rng.sample(range(len(gene)), 2)
                gene[a], gene[b] = gene[b], gene[a]
        return individual

    # ---- next generation ----
    def next_generation(self, stagnating=False):
        self.mutation_rate = (
            self.base_mutation_rate * self.hypermutation_factor
            if stagnating else self.base_mutation_rate
        )
        ranked = sorted(range(self.pop_size),
                        key=lambda i: self.fitnesses[i], reverse=True)
        new_pop = [[g[:] for g in self.population[i]]
                   for i in ranked[:self.elite_count]]
        while len(new_pop) < self.pop_size:
            p1 = self.tournament_selection()
            p2 = self.tournament_selection()
            c1, c2 = self.crossover(p1, p2)
            new_pop.append(self.mutate(c1))
            if len(new_pop) < self.pop_size:
                new_pop.append(self.mutate(c2))
        self.population = new_pop

    # ---- restart (random immigrants) for deep stagnation ----
    def restart(self, keep=None):
        keep = self.elite_count if keep is None else keep
        ranked = sorted(range(self.pop_size),
                        key=lambda i: self.fitnesses[i], reverse=True)
        survivors = [[g[:] for g in self.population[i]] for i in ranked[:keep]]
        fresh = [self._random_individual()
                 for _ in range(self.pop_size - keep)]
        self.population = survivors + fresh

    def best_index(self):
        return max(range(self.pop_size), key=lambda i: self.fitnesses[i])

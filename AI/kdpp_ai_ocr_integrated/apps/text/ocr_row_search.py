"""Bounded strict row searches after necessary anchor geometry pruning.

The caller remains responsible for validating complete annotation provenance,
region containment, and strict polygon input geometry. This helper only finds
disjoint original annotation indices; it does not repair polygons or tokens.
"""

from __future__ import annotations

import math
from collections import Counter


_MAX_ROW_SEARCH_STATES = 1024


def physical_row_options(text, words, *, tokenise):
    """Find every strict physical token partition, or fail closed on budget.

    Each possible longest top-edge anchor supplies necessary pair conditions.
    The existing complete-row verifier still decides every returned partition.
    No quantisation relaxation is used. Equal annotations retain their distinct
    original indices, and all anchor pools share one 1024-state budget.
    """
    # Keep this import local: ocr_geometry may call this bounded fallback.
    from apps.text.ocr_geometry import _physical_row

    row = tokenise(text)
    if not row:
        return ()
    sequences = tuple(tokenise(word.text) for word in words)
    matching = tuple(
        index for index, sequence in enumerate(sequences)
        if sequence and len(words[index].vertices) == 4
        and any(row[start:start + len(sequence)] == sequence
                for start in range(len(row) - len(sequence) + 1))
    )
    lengths = {
        index: math.dist(words[index].vertices[0], words[index].vertices[1])
        for index in matching
    }
    matching = tuple(index for index in matching if lengths[index] > 0)
    required = Counter(row)

    # A token with exactly one possible annotation proves that annotation is
    # mandatory, including when it is part of a joined annotation.
    mandatory = {
        supporters[0]
        for token in required
        if len(supporters := [index for index in matching if token in sequences[index]]) == 1
    }

    pools = {}
    for anchor_index in matching:
        anchor = words[anchor_index]
        if any(lengths[index] > lengths[anchor_index] for index in mandatory):
            continue
        (x0, y0), (x1, y1), *_ = anchor.vertices
        length = lengths[anchor_index]
        direction = ((x1 - x0) / length, (y1 - y0) / length)

        def projected_left(index):
            return min(direction[0] * x + direction[1] * y
                       for x, y in words[index].vertices)

        pool = []
        for index in matching:
            if lengths[index] > length:
                continue
            # Anchor first fixes the verifier's longest-edge tie to this
            # candidate frame. The synthetic text follows its projected order;
            # no row-token position or reading-order assumption is imposed.
            pair = (anchor_index,) if index == anchor_index else (anchor_index, index)
            ordered = sorted(pair, key=projected_left)
            pair_text = " ".join(words[item].text for item in ordered)
            if _physical_row(pair_text, tuple(words[item] for item in pair), tokenise=tokenise):
                pool.append(index)
        pool = tuple(pool)
        available = Counter(token for index in pool for token in sequences[index])
        if (anchor_index not in pool or not mandatory.issubset(pool)
                or not required <= available):
            continue
        # Identical pools need one search, while retaining every possible
        # actual anchor that can occur in the final selected partition.
        pools.setdefault(pool, set()).add(anchor_index)

    options = {}
    state_count = 0
    for pool, anchors in pools.items():
        pending = [(0, ())]
        seen = set()
        while pending:
            position, chosen = pending.pop()
            signature = (position, frozenset(chosen))
            if signature in seen:
                continue
            if state_count >= _MAX_ROW_SEARCH_STATES:
                return ()
            seen.add(signature)
            state_count += 1
            if position == len(row):
                selected = tuple(words[index] for index in chosen)
                if anchors.intersection(chosen) and _physical_row(text, selected, tokenise=tokenise):
                    options[frozenset(chosen)] = chosen
                continue
            for index in pool:
                sequence = sequences[index]
                if index not in chosen and row[position:position + len(sequence)] == sequence:
                    pending.append((position + len(sequence), (*chosen, index)))
    return tuple(options.values())

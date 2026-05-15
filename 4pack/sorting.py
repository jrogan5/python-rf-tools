#!/usr/bin/env python3
import re
import sys
from pathlib import Path
import numpy as np
from rf_measurements.utils.mdif import read_mdif, write_mdif

def _load(mdif_path):
    meta, blocks = read_mdif(mdif_path)
    freq = blocks[0]["freq"]
    grp = {}
    for m, b in zip(meta, blocks):
        key = (int(m["SN"]), float(m["Temperature"]))
        grp.setdefault(key, []).append((int(m["Path"]), b["s21_db"]))
    return freq, grp


def _avg_path(path_blocks):
    path_blocks.sort(key=lambda p: p[0])                # 1‑4 order
    return np.mean(np.vstack([g for _, g in path_blocks]), axis=0)


def _sort_index(groups):
    """Map SN → index (0 = lowest ambient gain).  Missing ambient → last."""
    scores = [(sn, np.mean(_avg_path(p)))               # only compare at ambient
              for (sn, t), p in groups.items() if (t == 23 or t==25)]

    scores.sort(key=lambda x: x[1])                     # lowest → highest
    idx = {sn: i for i, (sn, _) in enumerate(scores)}   # existing SNs

    # give every other SN a large index (they will appear after the sorted ones)
    max_idx = len(idx)
    for sn, _ in scores:                               # ensure all ambient SNs present
        idx.setdefault(sn, max_idx)
    return idx, max_idx


def _build(freq, groups, idx, max_idx):
    # order by idx; SNs without ambient get max_idx (i.e. placed last)
    ordered = sorted(groups.keys(),
                     key=lambda k: idx.get(k[0], max_idx))

    out = []
    for sn, temp in ordered:
        rows = [{"freq": f, "s21_avg_db": g}
                for f, g in zip(freq, _avg_path(groups[(sn, temp)]))]
        meta = {"Temperature": temp,
                "SortIndex": idx.get(sn, max_idx),
                "!SN": sn}   # same index for all temps
        out.append((meta, rows))
    return out


def main(in_mdif: Path, out_mdif: Path):
    freq, groups = _load(in_mdif)
    idx, max_idx = _sort_index(groups)                 # compute sorting
    blocks = _build(freq, groups, idx, max_idx)         # build output
    write_mdif(out_mdif,
               blocks=blocks,
               header_tokens=["%freq(real)", "s21_avg_db(real)"])


if __name__ == "__main__":
    print("=============================")
    print("rf_measurements.4pack.sorting")
    print("=============================")
    inpath = Path(input("Enter path to input .mdif file (containing measurements of s21_db): "))
    outpath = Path(input("Enter desired path with filename for output mdif file: "))
    main(inpath, outpath)
from utils.mdif import *
import numpy as np
from pathlib import Path

MDIF_PATH = Path(r"G:\Everyone\James\Lightspeed\Nicolas\dbf s11 plotting\dbf_s11_unpowered.mdif")
VAR_TO_SPLIT = "ADC"
OUT_DIR = Path(r"G:\Everyone\James\Lightspeed\Nicolas\dbf s11 plotting\measurements_by_ADC")

def main():
    meta_arr, data_blocks = read_mdif(MDIF_PATH)


    blocks: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []

    for meta, col_dict in zip(meta_arr,data_blocks):

        n_rows = len(next(iter(col_dict.values())))

        rows: List[Dict[str, Any]] = []
        for i in range(n_rows):
            row: Dict[str, Any] = {col: float(arr[i]) for col, arr in col_dict.items()}
            rows.append(row)
        blocks.append((meta,rows))
    split_groups = split_mdif_by_var(blocks, VAR_TO_SPLIT)
    for idx, group in enumerate(split_groups):

        val = group[0][0][VAR_TO_SPLIT]
        header_tokens = list(group[0][1][0].keys())


        # Pick a file name that is easy to read back later.
        out_path = OUT_DIR / f"{MDIF_PATH.stem}_{VAR_TO_SPLIT}_{int(val)}.mdif"

        write_mdif(
            out_path=out_path,
            blocks=group,
            header_tokens=header_tokens,
            kind="split",
        )
if __name__ == "__main__":
    main()


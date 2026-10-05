"""ILLUSTRATIVE subprocess stub for adapter tests; never a scientific pocket detector."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time


def main() -> int:
    """Emit a small fpocket-format test double or an explicitly requested failure mode."""
    mode = os.environ.get("FPOCKET_STUB_MODE", "normal")
    if len(sys.argv) == 1:
        print("fpocket " + ("3.0" if mode == "version" else "4.0"))
        return 0
    print("***** POCKET HUNTING BEGINS *****", flush=True)
    if mode == "timeout":
        time.sleep(60)
    if mode == "failed":
        print("deliberate executable failure", file=sys.stderr)
        return 9
    if mode == "internal":
        print("Error in creating clustering tree", file=sys.stderr)
        print("no pockets found")
    elif mode != "no_output":
        pdb = Path("receptor.pdb").read_text()
        output = Path("receptor_out")
        (output / "pockets").mkdir(parents=True)
        (output / "receptor_out.pdb").write_text(pdb)
        (output / "receptor_pockets.pqr").write_text("HEADER ILLUSTRATIVE STUB\nTER\nEND\n")
        info = []
        if mode == "empty":
            print("! No Pockets Found while refining", file=sys.stderr)
        else:
            for number, residue in ((1, 74), (2, 75)):
                lines = [line for line in pdb.splitlines() if line.startswith("ATOM  ") and int(line[22:26]) == residue]
                (output / f"pockets/pocket{number}_atm.pdb").write_text("\n".join(lines) + "\nTER\nEND\n")
                ca = next(line for line in lines if line[12:16].strip() == "CA")
                xyz = [float(ca[i:i + 8]) for i in (30, 38, 46)]
                spheres = [f"ATOM  {serial:5d}    C STP  {number:4d}    "
                           f"{xyz[0] + shift:8.3f}{xyz[1] + shift:8.3f}{xyz[2] + shift:8.3f}    0.00     3.50"
                           for serial, shift in ((1, -2), (2, 2))]
                (output / f"pockets/pocket{number}_vert.pqr").write_text("\n".join(spheres) + "\nTER\nEND\n")
                info.append(f"Pocket {number} :\n\tScore : {0.9 / number}\n\tDruggability Score : 0.5\n"
                            "\tNumber of Alpha Spheres : 2\n\tVolume : 100.0\n\tExample new descriptor : 2.5\n")
        (output / "receptor_info.txt").write_text("\n".join(info) if mode != "malformed" else "broken output\n")
    print("***** POCKET HUNTING ENDS *****", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

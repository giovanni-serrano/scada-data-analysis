"""Inventory synthetic RAW files and verify their bytes before/after processing."""
import csv
from pathlib import Path

from .common import digest, write_csv


def inventory(root):
    root = Path(root)
    rows = [{"source_file": p.relative_to(root).as_posix(), "bytes": p.stat().st_size,
             "sha256": digest(p)} for p in sorted((root / "data/raw").glob("*.csv"))]
    if not rows:
        raise ValueError("No RAW files found.")
    write_csv(root / "data/interim/file_inventory.csv", rows, ["source_file", "bytes", "sha256"])
    return rows


def verify(root):
    root = Path(root)
    with (root / "data/interim/file_inventory.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected = {r["source_file"] for r in rows}
    actual = {p.relative_to(root).as_posix() for p in (root / "data/raw").glob("*.csv")}
    if expected != actual or not rows:
        raise ValueError("RAW file set changed.")
    for row in rows:
        path = root / row["source_file"]
        if path.stat().st_size != int(row["bytes"]) or digest(path) != row["sha256"]:
            raise ValueError(f"RAW bytes changed: {row['source_file']}")
    return rows

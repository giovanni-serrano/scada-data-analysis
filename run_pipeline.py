"""Run the compact synthetic demo. Existing generated data are never overwritten."""
import argparse
from pathlib import Path

from src.analyze_scada import analyze
from src.build_processed import build
from src.file_inventory import inventory, verify
from src.generate_synthetic_scada import generate
from src.read_scada_csv import read_records


def run(root, figures=True):
    root = Path(root)
    for relative in ["data/raw", "data/interim", "data/processed"]:
        path = root / relative
        if path.exists() and any(path.iterdir()):
            raise FileExistsError("Generated data already exist. Use --output-dir with a new directory.")
    print("Generating synthetic history...")
    generate(root)
    inventory(root)
    read_records(root)
    quality = build(root)
    result = analyze(root, figures=figures)
    verify(root)
    print(f"Completed: {quality['rows']} preserved rows; synthetic change detected={result['synthetic_change_detected']}.")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    run(args.output_dir.resolve())

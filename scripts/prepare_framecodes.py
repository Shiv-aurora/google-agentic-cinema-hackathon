"""Prepare and verify immutable frame-coded rehearsal sources; no AI calls."""
import argparse
import json
from pathlib import Path

from services.media.framecode import prepare_sources


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--destination", type=Path, default=Path("data/framecoded"))
    args = parser.parse_args()
    print(json.dumps({"verified_source_directory": str(prepare_sources(args.source, args.destination))}))

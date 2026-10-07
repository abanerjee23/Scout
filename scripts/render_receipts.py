"""Render synthetic fixture transcripts to PNG; never edits uploaded receipts."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from unloop.fixture_check import ROOT, load_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["development", "heldout", "all"], default="development")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "local" / "receipts")
    args = parser.parse_args()
    splits = ("development", "heldout") if args.split == "all" else (args.split,)
    count = 0
    for split in splits:
        seen = set()
        for case in load_dataset(split).cases:
            for document in case.documents:
                if document.source in seen:
                    continue
                seen.add(document.source)
                lines = (ROOT / document.source).read_text().splitlines()
                font = ImageFont.load_default(size=22)
                image = Image.new("RGB", (1100, max(500, len(lines) * 42 + 100)), "white")
                draw = ImageDraw.Draw(image)
                for number, line in enumerate(lines):
                    draw.text((35, 40 + number * 42), line, font=font, fill="#222222")
                target = args.output / split / (Path(document.source).stem + ".png")
                target.parent.mkdir(parents=True, exist_ok=True)
                image.save(target)
                count += 1
    print(f"Rendered {count} synthetic transcript images to {args.output}")
    print("Not representative of real receipt photos; replace/expand before vision quality claims.")


if __name__ == "__main__":
    main()

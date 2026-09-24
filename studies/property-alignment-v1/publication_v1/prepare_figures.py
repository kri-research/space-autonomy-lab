"""Normalize SVG trailing whitespace without changing its drawing tokens."""

from pathlib import Path
import argparse
import re


def normalize(raw):
    text = raw.decode("utf-8")
    result = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
    if re.sub(r"\s+", " ", text).strip() != re.sub(r"\s+", " ", result).strip():
        raise ValueError("SVG token stream changed")
    return result.encode("utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("destination", type=Path)
    args = p.parse_args()
    with args.destination.open("xb") as stream:
        stream.write(normalize(args.source.read_bytes()))


if __name__ == "__main__":
    main()

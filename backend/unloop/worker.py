"""Worker entry point; no queue processing until Phase 1."""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check this scaffold's entry point")
    args = parser.parse_args()
    if args.check:
        print("Worker entry point ready. PostgreSQL queue is not configured (Phase 1).")
        return
    parser.exit(2, "Queue processing is not implemented yet. Use --check for the scaffold.\n")


if __name__ == "__main__":
    main()

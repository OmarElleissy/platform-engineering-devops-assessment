"""Print only the whitelisted Terraform apply completion counts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import PolicyError, require

SUMMARY_PATTERN = re.compile(
    r"^Apply complete! Resources: ([0-9]+) added, "
    r"([0-9]+) changed, ([0-9]+) destroyed\.$",
    re.MULTILINE,
)


def extract_summary(text: str) -> tuple[int, int, int]:
    """Extract exactly one Terraform apply count line."""
    matches = SUMMARY_PATTERN.findall(text)
    require(len(matches) == 1, "exact Terraform apply summary was not found")
    return tuple(int(value) for value in matches[0])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-log", required=True)
    args = parser.parse_args()
    try:
        text = Path(args.apply_log).read_text(errors="replace")
        added, changed, destroyed = extract_summary(text)
    except (OSError, PolicyError) as exc:
        print(f"Terraform apply summary policy failed: {exc}", file=sys.stderr)
        return 1
    print(f"Terraform apply summary: add={added} change={changed} destroy={destroyed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate private ECR inventory and prepare bounded digest-only deletion batches."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from common import (
    PolicyError,
    append_github_values,
    load_json,
    mask_value,
    require,
    require_digest,
    require_sha,
)


def image_details(document: dict[str, Any]) -> list[dict[str, Any]]:
    details = document.get("imageDetails")
    require(isinstance(details, list), "ECR inventory has no imageDetails list")
    require(
        all(isinstance(item, dict) for item in details), "ECR inventory item is invalid"
    )
    return details


def find_tag(document: dict[str, Any], sha: str) -> str | None:
    """Return the digest for one exact SHA tag, failing on ambiguous inventory."""
    expected = require_sha(sha)
    matches = [
        item
        for item in image_details(document)
        if expected in item.get("imageTags", [])
    ]
    require(len(matches) <= 1, "exact immutable tag resolves to multiple images")
    if not matches:
        return None
    return require_digest(matches[0].get("imageDigest", ""))


def validated_inventory(document: dict[str, Any]) -> tuple[list[str], int]:
    """Reject untagged/non-SHA images and return unique digests and tag count."""
    digests: list[str] = []
    tag_count = 0
    for item in image_details(document):
        tags = item.get("imageTags")
        require(isinstance(tags, list) and tags, "untagged ECR image is forbidden")
        require(all(isinstance(tag, str) for tag in tags), "invalid ECR image tag")
        for tag in tags:
            require_sha(tag, "ECR image tag")
        digest = require_digest(item.get("imageDigest", ""))
        digests.append(digest)
        tag_count += len(tags)
    require(len(digests) == len(set(digests)), "duplicate ECR image digest")
    return digests, tag_count


def write_batches(digests: list[str], directory: str | Path) -> int:
    """Write digest-only AWS CLI batch files of no more than 100 images."""
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    batch_count = 0
    for offset in range(0, len(digests), 100):
        batch_count += 1
        batch = {
            "imageIds": [
                {"imageDigest": item} for item in digests[offset : offset + 100]
            ]
        }
        (destination / f"batch-{batch_count:04d}.json").write_text(json.dumps(batch))
    return batch_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("find", "inventory", "empty"))
    parser.add_argument("--json", required=True)
    parser.add_argument("--sha")
    parser.add_argument("--github-output")
    parser.add_argument("--batch-dir")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        document = load_json(args.json)
        require(isinstance(document, dict), "ECR JSON must be an object")
        if args.mode == "find":
            require(
                args.sha is not None and args.github_output,
                "find mode needs SHA and output",
            )
            digest = find_tag(document, args.sha)
            values = {"EXISTS": str(digest is not None).lower()}
            if digest:
                mask_value(digest)
                values["DIGEST"] = digest
            append_github_values(args.github_output, values)
            print(f"Exact SHA tag exists: {str(digest is not None).lower()}")
        elif args.mode == "inventory":
            require(
                args.batch_dir and args.github_output,
                "inventory mode needs batch paths",
            )
            digests, tag_count = validated_inventory(document)
            for digest in digests:
                mask_value(digest)
            batches = write_batches(digests, args.batch_dir)
            append_github_values(args.github_output, {"BATCH_COUNT": str(batches)})
            print(f"ECR image count: {len(digests)}")
            print(f"ECR tag count: {tag_count}")
        else:
            require(not image_details(document), "ECR repository is not empty")
            print("ECR image count: 0")
    except PolicyError as exc:
        print(f"ECR policy failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

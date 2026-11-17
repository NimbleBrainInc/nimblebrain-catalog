"""`registry build` writes the registry to a folder; `registry publish` uploads that folder.

The folder has two parts:

- `api/` holds each API object as `<key>.json`, because `v0.1/servers` and the
  folder `v0.1/servers/` cannot both exist as files. Publishing strips the suffix,
  so the object store holds the API paths exactly, each served as application/json.
- `site/` holds the catalog page and the 404 body under their own keys, each served
  with the content type `render.SITE_CONTENT_TYPES` gives it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from nimblebrain_registry.build import API_PREFIX, BuildError, Entry, build, parse_members
from nimblebrain_registry.render import SITE_CONTENT_TYPES, site

UPSTREAM = "https://registry.modelcontextprotocol.io"
SUFFIX = ".json"
CACHE_CONTROL = "public, max-age=300"


def fetch_upstream_versions(name: str, base: str = UPSTREAM) -> list[Entry]:
    url = f"{base}/{API_PREFIX}/servers/{urllib.parse.quote(name, safe='')}/versions"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return []
        raise BuildError(f"{name}: upstream returned HTTP {err.code}") from err
    if body.get("metadata", {}).get("nextCursor"):
        raise BuildError(
            f"{name}: upstream paginated the version list, which the build cannot read"
        )
    return body.get("servers", [])


def write(objects: dict[str, Any], out: Path) -> None:
    for key, body in objects.items():
        path = out / "api" / f"{key}{SUFFIX}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n")
    for key, text in site(objects[f"{API_PREFIX}/servers"]).items():
        path = out / "site" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def read(out: Path) -> dict[str, tuple[bytes, str]]:
    """Every object in a built folder: key → (body, content type)."""
    api = out / "api"
    objects = {
        path.relative_to(api).as_posix().removesuffix(SUFFIX): (
            path.read_bytes(),
            "application/json",
        )
        for path in sorted(api.rglob(f"*{SUFFIX}"))
    }
    for key, content_type in SITE_CONTENT_TYPES.items():
        path = out / "site" / key
        if path.is_file():
            objects[key] = (path.read_bytes(), content_type)
    return objects


def publish(out: Path, bucket: str, distribution: str | None) -> None:
    import boto3

    objects = read(out)
    missing = [k for k in (f"{API_PREFIX}/servers", *SITE_CONTENT_TYPES) if k not in objects]
    if missing:
        raise BuildError(f"{out} is not a complete build (missing {missing}); run `registry build`")

    s3 = boto3.client("s3")
    for key, (body, content_type) in objects.items():
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            CacheControl=CACHE_CONTROL,
        )

    # Remove API objects the build no longer produces, such as a server dropped from
    # the catalog. The site keys are a fixed set, so nothing outside the API goes stale.
    stale: list[str] = []
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix=f"{API_PREFIX}/"
    ):
        stale += [o["Key"] for o in page.get("Contents", []) if o["Key"] not in objects]
    for i in range(0, len(stale), 1000):
        s3.delete_objects(
            Bucket=bucket, Delete={"Objects": [{"Key": k} for k in stale[i : i + 1000]]}
        )

    if distribution:
        boto3.client("cloudfront").create_invalidation(
            DistributionId=distribution,
            InvalidationBatch={
                "Paths": {"Quantity": 1, "Items": ["/*"]},
                "CallerReference": str(time.time_ns()),
            },
        )
    print(f"published {len(objects)} objects, removed {len(stale)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="registry")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build the registry from members.yaml and upstream")
    b.add_argument("--members", type=Path, default=Path("members.yaml"))
    b.add_argument("--out", type=Path, default=Path("dist"))
    b.add_argument("--upstream", default=UPSTREAM)

    p = sub.add_parser("publish", help="upload a built registry to its bucket")
    p.add_argument("--out", type=Path, default=Path("dist"))
    p.add_argument("--bucket", required=True)
    p.add_argument("--distribution", help="CloudFront distribution to invalidate")

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            members = parse_members(yaml.safe_load(args.members.read_text()))
            objects = build(members, lambda name: fetch_upstream_versions(name, args.upstream))
            write(objects, args.out)
            print(f"built {len(objects)} API objects for {len(members)} servers in {args.out}")
        else:
            publish(args.out, args.bucket, args.distribution)
    except BuildError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

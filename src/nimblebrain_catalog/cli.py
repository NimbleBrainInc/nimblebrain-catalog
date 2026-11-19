"""`catalog build` writes the catalog to a folder; `catalog publish` uploads that folder.

The folder has two parts:

- `api/` holds each API object as `<key>.json`, because `v0.1/servers` and the
  folder `v0.1/servers/` cannot both exist as files. Publishing strips the suffix,
  so the object store holds the API paths exactly, each served as application/json.
- `site/` holds every other file under its own key: the catalog page, the 404 body,
  each plugin's zip, `marketplace.json`, and `.well-known/ai-catalog.json`, each
  served with the content type `content_type` gives it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from nimblebrain_catalog.build import (
    API_PREFIX,
    BuildError,
    Entry,
    build,
    parse_authored,
    parse_members,
)
from nimblebrain_catalog.plugins import distribution, parse_plugins
from nimblebrain_catalog.render import SITE_CONTENT_TYPES, site

UPSTREAM = "https://registry.modelcontextprotocol.io"
SUFFIX = ".json"
CACHE_CONTROL = "public, max-age=300"

# Key prefixes whose objects the build produces in full, so `publish` deletes any it
# no longer produces. The site's fixed keys never go stale.
MANAGED_PREFIXES = (f"{API_PREFIX}/", "plugins/")
# A plugin zip under its digest is named by indexes a host may have pinned, so
# `publish` keeps it after the build stops producing it. Pinned indexes live outside
# the managed prefixes and are kept the same way.
CONTENT_ADDRESSED = re.compile(r"^plugins/[^/]+/[0-9a-f]{64}\.zip$")

SUFFIX_CONTENT_TYPES = {
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".zip": "application/zip",
}


def content_type(key: str) -> str:
    if key in SITE_CONTENT_TYPES:
        return SITE_CONTENT_TYPES[key]
    for suffix, kind in SUFFIX_CONTENT_TYPES.items():
        if key.endswith(suffix):
            return kind
    raise BuildError(f"{key}: no content type for this file")


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


def read_authored(folder: Path) -> list[Entry]:
    """Every authored server in `folder/*.yaml`, in file-name order."""
    if not folder.is_dir():
        return []
    entries: list[Entry] = []
    for path in sorted(folder.glob("*.yaml")):
        entries += parse_authored(path.name, yaml.safe_load(path.read_text()))
    return entries


def write(
    objects: dict[str, Any],
    out: Path,
    files: dict[str, bytes] | None = None,
    plugins: dict[str, str] | None = None,
) -> None:
    """Write the API objects, the catalog page, and any other site files.

    `plugins` maps a server's name to the plugin that installs it, for the page.
    """
    for key, body in objects.items():
        path = out / "api" / f"{key}{SUFFIX}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n")
    listing = objects[f"{API_PREFIX}/servers"]
    pages = {k: v.encode() for k, v in site(listing, plugins).items()}
    for key, data in {**pages, **(files or {})}.items():
        path = out / "site" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


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
    site_dir = out / "site"
    if site_dir.is_dir():
        for path in sorted(p for p in site_dir.rglob("*") if p.is_file()):
            key = path.relative_to(site_dir).as_posix()
            objects[key] = (path.read_bytes(), content_type(key))
    return objects


def publish(out: Path, bucket: str, distribution: str | None) -> None:
    import boto3

    objects = read(out)
    missing = [k for k in (f"{API_PREFIX}/servers", *SITE_CONTENT_TYPES) if k not in objects]
    if missing:
        raise BuildError(f"{out} is not a complete build (missing {missing}); run `catalog build`")

    s3 = boto3.client("s3")
    for key, (body, kind) in objects.items():
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=kind,
            CacheControl=CACHE_CONTROL,
        )

    # Remove objects the build no longer produces, such as a server or plugin dropped
    # from the catalog. Only the managed prefixes are swept, and a zip under its
    # digest is never removed.
    stale: list[str] = []
    for prefix in MANAGED_PREFIXES:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            stale += [
                o["Key"]
                for o in page.get("Contents", [])
                if o["Key"] not in objects and not CONTENT_ADDRESSED.match(o["Key"])
            ]
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
    parser = argparse.ArgumentParser(prog="catalog")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser(
        "build", help="build the catalog from members.yaml, servers/, plugins, and upstream"
    )
    b.add_argument("--members", type=Path, default=Path("members.yaml"))
    b.add_argument("--servers", type=Path, default=Path("servers"))
    b.add_argument("--plugins", type=Path, default=Path("plugins.yaml"))
    b.add_argument("--plugin-dir", type=Path, default=Path("plugins"))
    b.add_argument("--out", type=Path, default=Path("dist"))
    b.add_argument("--upstream", default=UPSTREAM)

    p = sub.add_parser("publish", help="upload a built catalog to its bucket")
    p.add_argument("--out", type=Path, default=Path("dist"))
    p.add_argument("--bucket", required=True)
    p.add_argument("--distribution", help="CloudFront distribution to invalidate")

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            members = parse_members(yaml.safe_load(args.members.read_text()))
            authored = read_authored(args.servers)
            objects = build(
                members, lambda name: fetch_upstream_versions(name, args.upstream), authored
            )
            plugins = parse_plugins(yaml.safe_load(args.plugins.read_text()))
            listed = objects[f"{API_PREFIX}/servers"]["servers"]
            servers = {e["server"]["name"]: e["server"] for e in listed}
            files = distribution(plugins, servers, args.plugin_dir)
            write(objects, args.out, files, {p.server: p.name for p in plugins})
            count = len(members) + len(authored)
            print(
                f"built {len(objects)} API objects for {count} servers"
                f" and {len(plugins)} plugins in {args.out}"
            )
        else:
            publish(args.out, args.bucket, args.distribution)
    except BuildError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

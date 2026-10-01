"""Publish verified forcing files to the public R2 bucket. Dry run by default.

    python -m fishmip_cesm.upload --out-dir "$OUT_DIR"           # lists only
    python -m fishmip_cesm.upload --out-dir "$OUT_DIR" --publish

**The bucket is world-readable, so uploading is publishing.** A link that has
been handed out, cached or indexed cannot be recalled by deleting the object, so
nothing is sent until the deep verification has passed and someone has decided
to publish.

Credentials come from R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_ACCOUNT_ID,
are read at runtime only, and are never written to a file, logged, or placed on
a command line.
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from fishmip_cesm.naming import BUCKET, PREFIX

# <source_id>_<experiment_id>_<member>_<variable>_...
_EXPERIMENT_FIELD = 1


@dataclass(frozen=True)
class Credentials:
    access_key_id: str
    secret_access_key: str = field(repr=False)
    account_id: str

    @property
    def endpoint(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"


def credentials_from_env() -> Credentials:
    """Read R2 credentials from the environment, or say which one is missing."""
    names = ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ACCOUNT_ID")
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise RuntimeError(f"missing credentials: {', '.join(missing)}")
    return Credentials(*(os.environ[n] for n in names))


def plan_upload(filename: str) -> str:
    """The object key for a published file, derived from its own name.

    Refuses a name it cannot parse rather than guessing a prefix: a file under
    the wrong key is both invisible to anyone looking for it and awkward to
    withdraw once it has been published.
    """
    parts = filename.removesuffix(".nc").split("_")
    if len(parts) < 9 or not filename.endswith(".nc"):
        raise ValueError(f"not a FishMIP forcing filename: {filename}")
    return f"{PREFIX}/{parts[_EXPERIMENT_FIELD]}/{filename}"


def needs_upload(local_size: int, remote_size: int | None) -> bool:
    """Whether to send this file. Equal sizes are treated as already there."""
    return remote_size != local_size


def _client(credentials: Credentials):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=credentials.endpoint,
        aws_access_key_id=credentials.access_key_id,
        aws_secret_access_key=credentials.secret_access_key,
        region_name="auto",
    )


def _remote_size(client, key: str) -> int | None:
    from botocore.exceptions import ClientError

    try:
        return client.head_object(Bucket=BUCKET, Key=key)["ContentLength"]
    except ClientError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="actually upload. Without this, nothing is sent.",
    )
    args = parser.parse_args()

    paths = sorted(args.out_dir.glob("*.nc"))
    if not paths:
        print(f"no files in {args.out_dir}")
        return 2

    try:
        keys = {path: plan_upload(path.name) for path in paths}
    except ValueError as error:
        print(f"refusing to upload: {error}")
        return 2

    if not args.publish:
        total = sum(p.stat().st_size for p in paths) / 1e9
        print(f"DRY RUN -- nothing will be sent.\n")
        print(f"{len(paths)} file(s), {total:.1f} GB, to s3://{BUCKET}/{PREFIX}/")
        for path in paths[:5]:
            print(f"  {path.name}\n    -> {keys[path]}")
        if len(paths) > 5:
            print(f"  ... and {len(paths) - 5} more")
        print(
            "\nThis bucket is public. Confirm the deep verification passed and"
            "\nthat the filenames are signed off before passing --publish:"
            "\n  python -m fishmip_cesm.verify_output --out-dir"
            f" {args.out_dir} --deep"
        )
        return 0

    try:
        credentials = credentials_from_env()
    except RuntimeError as error:
        print(error)
        return 2

    client = _client(credentials)
    sent = skipped = 0
    for path in paths:
        key = keys[path]
        local = path.stat().st_size
        if not needs_upload(local, _remote_size(client, key)):
            skipped += 1
            continue
        print(f"  {path.name} -> {key} ({local / 1e9:.2f} GB)")
        client.upload_file(str(path), BUCKET, key)
        sent += 1

    print(f"\nuploaded {sent}, already present {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

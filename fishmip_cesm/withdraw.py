"""Remove published objects for one scenario. Dry run by default.

    python -m fishmip_cesm.withdraw --scenario g6-1p5k-mcb
    python -m fishmip_cesm.withdraw --scenario g6-1p5k-mcb --confirm

Publishing cannot be undone, but data known to be wrong is worse left in place
than withdrawn: a file that is absent fails loudly, and a file that is present
and mislabelled is analysed without anyone noticing. This exists for that case.

It deletes one scenario's prefix and nothing else. The scenario token is
checked before any call is made, because a prefix that escapes its own
directory would take the whole published set with it.

Credentials come from R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_ACCOUNT_ID,
are read at runtime only, and are never written to a file, logged, or placed on
a command line.
"""

import argparse
import sys

from fishmip_cesm.naming import BUCKET, PREFIX
from fishmip_cesm.upload import _client, credentials_from_env

# One path segment: letters, digits, dots and dashes. Anything else -- a
# slash, a wildcard, "..", or nothing at all -- could reach beyond the
# scenario being withdrawn.
_SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")


def object_prefix(scenario: str) -> str:
    """The bucket prefix holding exactly one scenario's files."""
    if not scenario or not scenario.strip():
        raise ValueError("no scenario given")
    if scenario == PREFIX:
        raise ValueError(f"{scenario!r} is the whole published set, not a scenario")
    if scenario in (".", "..") or not set(scenario) <= _SAFE:
        raise ValueError(f"unsafe scenario token: {scenario!r}")
    # The trailing slash matters: without it the prefix also matches a
    # sibling directory whose name merely starts the same way.
    return f"{PREFIX}/{scenario}/"


def _keys_under(client, prefix: str) -> list[str]:
    keys, token = [], None
    while True:
        page = client.list_objects_v2(
            Bucket=BUCKET, Prefix=prefix, **({"ContinuationToken": token} if token else {})
        )
        keys.extend(item["Key"] for item in page.get("Contents", []))
        if not page.get("IsTruncated"):
            return keys
        token = page["NextContinuationToken"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="actually delete. Without this, nothing is removed.",
    )
    args = parser.parse_args()

    try:
        prefix = object_prefix(args.scenario)
    except ValueError as error:
        print(f"refusing to withdraw: {error}")
        return 2

    try:
        credentials = credentials_from_env()
    except RuntimeError as error:
        print(error)
        return 2

    client = _client(credentials)
    keys = _keys_under(client, prefix)
    if not keys:
        print(f"nothing published under s3://{BUCKET}/{prefix}")
        return 0

    print(f"{len(keys)} object(s) under s3://{BUCKET}/{prefix}\n")
    for key in keys:
        print(f"  {key}")

    if not args.confirm:
        print(
            f"\nDRY RUN -- nothing removed. {len(keys)} object(s) would be"
            "\ndeleted permanently, and anyone holding a link would lose it."
            "\nPass --confirm to go ahead."
        )
        return 0

    removed = 0
    for start in range(0, len(keys), 1000):  # the API's limit per call
        batch = keys[start : start + 1000]
        client.delete_objects(
            Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in batch]}
        )
        removed += len(batch)
    print(f"\nwithdrew {removed} object(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

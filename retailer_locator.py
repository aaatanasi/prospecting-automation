"""Normalize a local store-locator JSON file into retailer and branch CSVs."""
import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

LOCATION_FIELDS = ("retailer", "store", "street", "street_2", "city", "region", "postal_code", "country", "full_address")
SUMMARY_FIELDS = ("retailer", "branch_count", "single_branch_address", "branch_cities", "branch_countries", "branch_addresses")
# Synthetic examples only. Keep aliases explicit and anchored to avoid merging unrelated stores.
ALIASES = ((re.compile(r"^Aster & Alder(?:\s+[–—-]\s+.*)?$", re.I), "Aster & Alder"),)


def clean(value):
    """Use scalar text only; ignore nested or unexpected values."""
    return str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def arrays(obj):
    """Find lists at any depth in a JSON response."""
    if isinstance(obj, list):
        yield obj
        for item in obj:
            yield from arrays(item)
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from arrays(value)


def store_like(item):
    return (isinstance(item, dict) and bool(clean(item.get("name")) or clean(item.get("store_name")))
            and any(item.get(k) is not None and item.get(k) != "" for k in
                    ("address_line_1", "address", "city", "country", "latitude", "postal_code")))


def extract_stores(payload):
    """Use the largest store-shaped list, avoiding smaller metadata lists."""
    candidates = ([row for row in group if store_like(row)] for group in arrays(payload))
    return max(candidates, key=len, default=[])


def group_name(name):
    for pattern, canonical in ALIASES:
        if pattern.fullmatch(name):
            return canonical
    return name


def normalise(item):
    address = item.get("address")
    if isinstance(address, dict):
        address = address.get("street") or address.get("line1")
    row = dict(
        store=clean(item.get("name")) or clean(item.get("store_name")),
        street=clean(item.get("address_line_1")) or clean(address),
        street_2=clean(item.get("address_line_2")),
        city=clean(item.get("city")),
        region=clean(item.get("state")),
        postal_code=clean(item.get("postal_code")),
        country=clean(item.get("country")),
    )
    row["retailer"] = group_name(row["store"])
    row["full_address"] = ", ".join(row[k] for k in LOCATION_FIELDS[2:-1] if row[k])
    return row


def join_unique(values):
    return " | ".join(dict.fromkeys(v for v in values if v))


def consolidate(items):
    stores, seen, groups = [], set(), defaultdict(list)
    for raw in items:
        branch = normalise(raw)
        identity = tuple(" ".join(branch[key].casefold().split()) for key in LOCATION_FIELDS[1:-1])
        if identity in seen:
            continue
        seen.add(identity)
        groups[branch["retailer"]].append(branch)
        stores.append(branch)
    summary = [
        {"retailer": retailer, "branch_count": len(branches),
         "single_branch_address": branches[0]["full_address"] if len(branches) == 1 else "",
         "branch_cities": join_unique(b["city"] for b in branches),
         "branch_countries": join_unique(b["country"] for b in branches),
         "branch_addresses": join_unique(b["full_address"] for b in branches)}
        for retailer, branches in sorted(groups.items(), key=lambda pair: pair[0].casefold())
    ]
    review = [{**b, "missing_fields": " | ".join(k for k in ("street", "city", "country") if not b[k])}
              for b in stores if not all(b[k] for k in ("street", "city", "country"))]
    return summary, stores, review


def spreadsheet_safe(value):
    """Treat formula-like input as text when a spreadsheet opens a CSV."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: spreadsheet_safe(row[k]) for k in fields} for row in rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True, help="local JSON file")
    parser.add_argument("--output", type=Path, required=True, help="local output folder")
    args = parser.parse_args(argv)
    try:
        with args.json.open(encoding="utf-8-sig") as handle:
            stores = extract_stores(json.load(handle))
        if not stores:
            parser.error("No recognizable store records found in the JSON input.")
        summary, branches, review = consolidate(stores)
        args.output.mkdir(parents=True, exist_ok=True)
        write_csv(args.output / "retailers.csv", SUMMARY_FIELDS, summary)
        write_csv(args.output / "locations.csv", LOCATION_FIELDS, branches)
        write_csv(args.output / "missing_information.csv", (*LOCATION_FIELDS, "missing_fields"), review)
    except (OSError, ValueError, RecursionError) as exc:
        parser.error(str(exc))
    print(f"{len(stores)} records found; {len(stores)-len(branches)} duplicates removed; "
          f"{len(summary)} retailers; {len(review)} locations for review.")


if __name__ == "__main__":
    main()

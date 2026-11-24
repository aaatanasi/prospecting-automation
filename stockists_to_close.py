#!/usr/bin/env python3
"""Parse a local, text-based stockist HTML fixture into import and review CSVs."""

import argparse
import csv
import re
from html.parser import HTMLParser
from pathlib import Path

EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?|\d{2,4}[\s.-])\d[\d\s().-]{5,}\d(?!\w)")
WEB = re.compile(r"(?:https?://)?www\.[\w.-]+\.[a-z]{2,}(?:/[^\s]*)?", re.I)
US_CITY = re.compile(r"(?P<city>[A-Za-z .'-]+),?\s+(?P<state>AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\s+(?P<zip>\d{5}(?:-\d{4})?)\b", re.I)
COUNTRIES = ("United Kingdom", "Australia", "Belgium", "Canada", "France", "Greece",
             "Ireland", "Japan", "Netherlands", "Switzerland", "Turks & Caicos Islands",
             "Turks and Caicos Islands")
IGNORE = {"online", "united states", "international", "stockists", "new stockists",
          "stores", "store locator", "subscribe", "alabama", "california", "new york",
          "florida", "texas", *(c.casefold() for c in COUNTRIES)}
END = {"sign up", "customer service", "privacy policy", "returns & exchanges"}
HEADERS = ["Company", "Phone", "Email", "URL", "Address", "City", "State", "Zip",
           "Country", "custom.Data Source", "Source File", "Review"]
SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}
BLOCK = {"br", "p", "li", "h1", "h2", "h3", "h4", "div", "section", "article", "main"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}


def clean(value):
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip(" -|\t")


class Page(HTMLParser):
    """Collect page text and prioritize main, role=main, section, article, body."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.chunks = [[] for _ in range(6)]
        self.title = []
        self.brand = ""

    def add(self, data):
        if any(tag in SKIP or tag == "head" for tag, _ in self.stack):
            return
        self.chunks[5].append(data)
        for _, rank in self.stack:
            if rank is not None:
                self.chunks[rank].append(data)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("property") == "og:site_name":
            self.brand = clean(attrs.get("content") or "")
        if tag in BLOCK:
            self.add("\n")
        rank = (0 if tag == "main" else 1 if attrs.get("role") == "main" else
                2 if "shopify-section" in (attrs.get("class") or "").split() else
                3 if tag == "article" else 4 if tag == "body" else None)
        if tag not in VOID:
            self.stack.append((tag, rank))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in BLOCK:
            self.add("\n")
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if any(tag == "title" for tag, _ in self.stack):
            self.title.append(data)
        self.add(data)

    def lines(self):
        parts = next((c for c in self.chunks if clean("".join(c))), [])
        return [value for line in "".join(parts).splitlines() if (value := clean(line))]

    def brand_name(self):
        title = clean("".join(self.title))
        return self.brand or (clean(re.split(r"[–|]", title)[-1]) if re.search("[–|]", title) else "") or "Unknown brand"


def is_contact(line):
    return bool(PHONE.search(line) or EMAIL.search(line) or WEB.search(line))


def looks_address(line):
    return bool(re.search(r"\b\d{1,6}\b|\b(?:street|st\.?|road|rd\.?|avenue|ave\.?|blvd|lane|ln\.?|drive|dr\.?|suite|highway|hwy|plaza)\b", line, re.I))


def extract(lines, brand, source):
    results = []
    pending = []
    started = False
    for line in lines:
        lower = line.casefold()
        if lower in END:
            if started:
                break
            continue
        if lower in IGNORE:
            continue
        if not started and (is_contact(line) or looks_address(line)):
            started = True
        if not started:
            pending.append(line)
            if len(pending) > 3:
                pending.pop(0)
            continue
        pending.append(line)
        if not is_contact(line):
            continue
        chunk, pending = pending, []
        contacts = [x for x in chunk if is_contact(x)]
        other = [x for x in chunk if not is_contact(x)]
        if not other:
            continue
        start = next((i for i, x in enumerate(other) if looks_address(x)), None)
        name = other[start - 1] if start is not None and start > 0 else other[0]
        parts = other[start:] if start is not None else []
        if name in parts:
            parts.remove(name)
        address = ", ".join(parts)
        match = US_CITY.search(address)
        country = "United States" if match else next((c for c in COUNTRIES if c.casefold() in address.casefold()), "")
        phone = next((m.group().strip() for x in contacts if (m := PHONE.search(x))), "")
        email = next((m.group() for x in contacts if (m := EMAIL.search(x))), "")
        website = next((m.group() for x in contacts if (m := WEB.search(x))), "")
        flags = []
        if not address:
            flags.append("Online/no address")
        if not match and address:
            flags.append("Check location fields")
        if len(other) > 7 or len(name) > 75:
            flags.append("Check record boundary")
        values = [name, phone, email, website, address, clean(match["city"]) if match else "",
                  match["state"].upper() if match else "", match["zip"] if match else "",
                  country, brand, source, "; ".join(flags)]
        results.append(dict(zip(HEADERS, values)))
    if pending and results:
        results[-1]["Review"] = "; ".join(filter(None, (results[-1]["Review"], "Unparsed trailing text: " + " / ".join(pending[:6]))))
    return list({(r["Company"].casefold(), r["Address"].casefold()): r for r in results if r["Company"]}.values())


def safe_cell(value):
    # Prevent user-supplied fixture text from becoming a formula in a workbook.
    return "'" + value if value and value.lstrip().startswith(("=", "+", "-", "@")) else value


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows({key: safe_cell(value) for key, value in row.items()} for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, help="Local HTML file; no network requests")
    parser.add_argument("--brand", help="Optional source brand label")
    parser.add_argument("--output", type=Path, default=Path("stockist_outputs"))
    args = parser.parse_args()
    if not args.fixture.is_file() or args.fixture.suffix.casefold() not in {".html", ".htm"}:
        parser.error("Choose an existing local HTML fixture")
    page = Page()
    page.feed(args.fixture.read_text(encoding="utf-8"))
    page.close()
    rows = extract(page.lines(), clean(args.brand) if args.brand else page.brand_name(), args.fixture.name)
    if not rows:
        parser.error("No stockists detected. The input may require a different layout parser.")
    args.output.mkdir(parents=True, exist_ok=True)
    flagged = [r for r in rows if r["Review"]]
    write_csv(args.output / "close_import.csv", rows)
    write_csv(args.output / "review.csv", flagged)
    print(f"Found {len(rows)} possible stockists; {len(flagged)} flagged for review.")


if __name__ == "__main__":
    main()

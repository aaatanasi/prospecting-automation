"""Parse saved accordion directory HTML and export a reviewable CSV."""
import argparse
import csv
import re
from html.parser import HTMLParser
from pathlib import Path

class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []
    def text(self):
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)
    def find(self, predicate):
        for c in self.children:
            if isinstance(c, Node):
                if predicate(c):
                    yield c
                yield from c.find(predicate)
    def has_class(self, name):
        return name in self.attrs.get('class', '').split()

class Document(HTMLParser):
    VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag == 'br':
            n.children.append('\n')
        if tag not in self.VOID:
            self.stack.append(n)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break
    def handle_data(self, data):
        self.stack[-1].children.append(data)

def clean(text):
    return ' '.join(text.replace('\u200d', '').replace('\u200b', '').split())


LOCATION = re.compile(r"([A-Za-z][A-Za-z .-]+),\s*[A-Z]{2}(?:\s+\d{5}(?:-\d{4})?)?")
FIELDS = ["Organization", "City", "Region", "Source", "Review"]


def extract_records(html, source):
    records = []
    for item in Document(html).root.find(lambda n: n.has_class("accordion-item")):
        title = next(item.find(lambda n: n.has_class("accordion-item__title")), None)
        body = next(item.find(lambda n: n.has_class("accordion-item__description")), None)
        if title is None or body is None:
            continue
        region = clean(title.text())
        record = None
        for p in body.find(lambda n: n.tag == "p"):
            name = clean(" ".join(n.text() for n in p.find(lambda n: n.tag in {"b", "strong"})))
            if name:
                record = dict(zip(FIELDS, [name, "", region, source, ""]))
                records.append(record)
                location = clean(p.text()).removeprefix(name).strip()
            elif record is not None and next(p.find(lambda n: n.tag == "a"), None) is None:
                location = clean(p.text())
            else:
                continue
            match = LOCATION.fullmatch(location)
            if match and not record["City"]:
                record["City"] = match.group(1)
    if not records:
        raise ValueError("No accordion entries matched the expected structure.")
    for r in records:
        if not r["City"]:
            r["Review"] = "Verify location"
    return records


def csv_safe(value):
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("input", type=Path, help="Saved local UTF-8 HTML")
    cli.add_argument("output", type=Path, help="CSV destination")
    args = cli.parse_args()
    if args.input.resolve() == args.output.resolve():
        cli.error("Input and output must be different files.")
    try:
        rows = extract_records(args.input.read_text(encoding="utf-8-sig"), "Expandable directory")
    except (OSError, ValueError) as exc:
        cli.error(str(exc))
    with args.output.open("w", encoding="utf-8", newline="") as dest:
        writer = csv.DictWriter(dest, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({key: csv_safe(value) for key, value in row.items()} for row in rows)


if __name__ == "__main__":
    main()

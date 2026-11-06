# -*- coding: utf-8 -*-
"""Regression tests for unique form-control IDs and explicit label associations."""
from __future__ import annotations

import os
import sys
import tempfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_form_ids_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


class FormMarkup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.label_targets = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "label" and values.get("for"):
            self.label_targets.append(values["for"])


def main():
    app.init()
    pages = {}
    with app.conn() as c:
        pages["loans"] = app.loans(c)
        pages["prices"] = app.prices(c)
        pages["parties"] = app.parties_page(c)
        pages["returns"] = app.returns_page(c)

    for route, markup in pages.items():
        parser = FormMarkup()
        parser.feed(markup)
        duplicates = sorted(value for value, count in Counter(parser.ids).items() if count > 1)
        assert not duplicates, f"{route}: duplicate HTML id values: {duplicates}"
        missing = sorted(set(parser.label_targets) - set(parser.ids))
        assert not missing, f"{route}: labels reference missing controls: {missing}"

    print("FORM CONTROL ID UNIQUENESS TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

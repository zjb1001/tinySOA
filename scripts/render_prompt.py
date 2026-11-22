#!/usr/bin/env python3
"""Render a prompt template by replacing ``{{VAR}}`` with environment values.

Usage:
    python3 scripts/render_prompt.py <template> <output>

Unknown placeholders are left untouched so a missing variable is visible in
the generated prompt instead of silently becoming an empty string.
"""
from __future__ import annotations

import os
import re
import sys

_PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: render_prompt.py <template> <output>", file=sys.stderr)
        return 2

    template_path, output_path = argv[1], argv[2]
    with open(template_path, encoding="utf-8") as template:
        text = template.read()

    def replace(match: re.Match[str]) -> str:
        value = os.environ.get(match.group(1))
        return match.group(0) if value is None else value

    rendered = _PLACEHOLDER.sub(replace, text)
    with open(output_path, "w", encoding="utf-8") as output:
        output.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

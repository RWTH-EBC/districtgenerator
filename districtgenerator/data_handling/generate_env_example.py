# -*- coding: utf-8 -*-
"""
Generate ``data/.env.CONFIG.EXAMPLE`` from ``config.py``.

``config.py`` is the single source of truth for all default values. The
EXAMPLE file is only a template: it lists every parameter that can be
overridden, with its default value, description and unit, all commented out.
It is generated from the source code and must not be edited by hand.

Usage
-----
    python -m districtgenerator.data_handling.generate_env_example          # write file
    python -m districtgenerator.data_handling.generate_env_example --check  # exit 1 if outdated

The script only parses ``config.py`` (ast/tokenize) and does not import it,
so it runs without the package dependencies.
"""

import ast
import io
import json
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config.py"
EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / ".env.CONFIG.EXAMPLE"

HEADER = """\
# =============================================================================
# AUTO-GENERATED FROM districtgenerator/data_handling/config.py - DO NOT EDIT.
# Regenerate with:
#   python -m districtgenerator.data_handling.generate_env_example
# =============================================================================
#
# This file is a TEMPLATE. It lists every parameter that can be overridden,
# together with its default value from config.py. All lines are commented out,
# so loading this file changes nothing.
#
# How to override values:
#   1. Create your own file in districtgenerator/data/, e.g. .env.CONFIG.MYPROJECT
#      (a file named .env.CONFIG is ignored by git and can be used for local tests).
#   2. Copy ONLY the lines you want to change from this template into it,
#      remove the leading "# " and adjust the value.
#   3. Load it: Datahandler(env_path=".env.CONFIG.MYPROJECT")
#
# Notes:
#   - Variable names are case-insensitive.
#   - Nested parameters use "__", e.g. SOLVER_OPTIONS__TIME_LIMIT=600.
#   - Central devices use the prefix "C_", decentral devices the prefix "D_".
#   - Lists are written as [a, b, c]. A single value is used for all years.
#   - "#" directly after "=" is part of the value (hex colors), not a comment.
"""


@dataclass
class EnvField:
    config_class: str
    name: str          # field name in config.py
    env_name: str      # name in the .env file (prefix + name, upper case)
    value: str         # default value formatted for .env
    comments: list     # comment lines (without leading "#")


def _read_comments(source):
    """Return {line number: comment text} and the set of lines that only hold a comment."""
    comments, comment_only = {}, set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            line_no = tok.start[0]
            comments[line_no] = tok.string.lstrip("#").strip()
            if tok.line.strip().startswith("#"):
                comment_only.add(line_no)
    return comments, comment_only


def _format_value(node):
    value = ast.literal_eval(node)
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value))
    if isinstance(value, str) and (value != value.strip() or " #" in value or value == ""):
        return json.dumps(value)   # quote, otherwise dotenv strips whitespace / cuts comments
    return str(value)


def _is_skipped(stmt):
    """Fields that cannot / should not be set via .env."""
    ann = ast.unparse(stmt.annotation)
    if ann.startswith("ClassVar"):
        return True
    if stmt.value is None:
        return True
    if isinstance(stmt.value, ast.Call):            # field(default_factory=...), Field(...)
        return True
    if isinstance(stmt.value, ast.Dict) and not stmt.value.keys:   # "HP: dict = {}" aggregators
        return True
    return False


def _env_prefix(class_node):
    for stmt in class_node.body:
        if (isinstance(stmt, ast.Assign) and any(getattr(t, "id", None) == "model_config" for t in stmt.targets)
                and isinstance(stmt.value, ast.Call)):
            for kw in stmt.value.keywords:
                if kw.arg == "env_prefix":
                    return ast.literal_eval(kw.value)
    return ""


def _global_config_order(tree):
    """Config classes in the order they appear in GlobalConfig."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "GlobalConfig":
            order = []
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign):
                    order.append(ast.literal_eval(stmt.annotation) if isinstance(stmt.annotation, ast.Constant)
                                 else ast.unparse(stmt.annotation))
            return order
    raise RuntimeError("GlobalConfig not found in config.py")


def collect_fields(config_path=CONFIG_PATH):
    """Parse config.py and return {class name: (docstring line, [EnvField, ...])} in GlobalConfig order."""
    source = Path(config_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    comments, comment_only = _read_comments(source)
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}

    result = {}
    for class_name in _global_config_order(tree):
        node = classes[class_name]
        prefix = _env_prefix(node)
        doc = (ast.get_docstring(node) or "").strip().splitlines()
        fields = []
        prev_end = node.body[0].end_lineno  # first statement (docstring) closes the gap
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and not _is_skipped(stmt):
                # comment block directly above the field (since the previous statement)
                above = [comments[i] for i in range(prev_end + 1, stmt.lineno) if i in comment_only]
                above = [c for c in above if c and not c.upper().startswith(("TODO", "!"))]
                inline = comments.get(stmt.end_lineno) if stmt.end_lineno not in comment_only else None
                name = stmt.target.id
                fields.append(EnvField(class_name, name, (prefix + name).upper(),
                                       _format_value(stmt.value), above + ([inline] if inline else [])))
            prev_end = stmt.end_lineno
        result[class_name] = (doc[0] if doc else "", prefix, fields)
    return result


def render(config_path=CONFIG_PATH):
    lines = [HEADER]
    for class_name, (doc, prefix, fields) in collect_fields(config_path).items():
        title = f"{class_name}" + (f' (prefix "{prefix}")' if prefix else "")
        lines += ["", "#" * 78, f"### {title}", f"### {doc}" if doc else "###", "#" * 78]
        for f in fields:
            lines.append("")
            lines += [f"# {c}" for c in f.comments]
            lines.append(f"# {f.env_name}={f.value}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    content = render()
    if "--check" in argv:
        current = EXAMPLE_PATH.read_text(encoding="utf-8") if EXAMPLE_PATH.exists() else ""
        if current != content:
            print(f"{EXAMPLE_PATH} is outdated or was edited by hand. "
                  f"Run: python -m districtgenerator.data_handling.generate_env_example")
            return 1
        print("EXAMPLE is up to date.")
        return 0
    EXAMPLE_PATH.write_text(content, encoding="utf-8", newline="\n")
    print(f"Written: {EXAMPLE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

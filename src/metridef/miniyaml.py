"""A tiny, dependency-free YAML subset.

This is *not* a general YAML implementation. It supports exactly the structures
a metric-definition file needs: block mappings, block sequences, nested
mappings inside sequence items, inline flow lists (``[a, b]``), and the scalar
types str/int/float/bool/null. That is enough to read a definitions file
without pulling in PyYAML, and small enough to be audited and property-tested.

The dumper always double-quotes string scalars, which guarantees that
``load(dump(x)) == x`` for any supported structure. The loader additionally
accepts bare (unquoted) strings so hand-written files stay comfortable.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["load", "dump", "YAMLError"]


class YAMLError(ValueError):
    pass


_INT_RE = re.compile(r"^[+-]?[0-9]+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+(?:[eE][+-]?[0-9]+))$")
_BARE_SAFE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\- ]*$")


# --------------------------------------------------------------------------- #
# Dumping
# --------------------------------------------------------------------------- #
def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _dump_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return _quote(v)
    raise YAMLError(f"unsupported scalar type: {type(v).__name__}")


def _is_scalar(v: Any) -> bool:
    return v is None or isinstance(v, (bool, int, float, str))


def _dump(obj: Any, indent: int, out: list[str]) -> None:
    pad = "  " * indent
    if isinstance(obj, dict):
        if not obj:
            out.append(f"{pad}{{}}")
            return
        for k, v in obj.items():
            key = str(k)
            if _is_scalar(v):
                out.append(f"{pad}{key}: {_dump_scalar(v)}")
            elif isinstance(v, (list, tuple)):
                if not v:
                    out.append(f"{pad}{key}: []")
                elif all(_is_scalar(x) for x in v):
                    out.append(f"{pad}{key}: [{', '.join(_dump_scalar(x) for x in v)}]")
                else:
                    out.append(f"{pad}{key}:")
                    _dump_seq(list(v), indent + 1, out)
            elif isinstance(v, dict):
                out.append(f"{pad}{key}:")
                _dump(v, indent + 1, out)
            else:
                raise YAMLError(f"unsupported value type: {type(v).__name__}")
    else:
        raise YAMLError("top-level value must be a mapping")


def _dump_seq(items: list[Any], indent: int, out: list[str]) -> None:
    pad = "  " * indent
    for item in items:
        if _is_scalar(item):
            out.append(f"{pad}- {_dump_scalar(item)}")
        elif isinstance(item, dict):
            if not item:
                out.append(f"{pad}- {{}}")
                continue
            first = True
            for k, v in item.items():
                key = str(k)
                lead = f"{pad}- " if first else f"{pad}  "
                first = False
                if _is_scalar(v):
                    out.append(f"{lead}{key}: {_dump_scalar(v)}")
                elif isinstance(v, (list, tuple)) and all(_is_scalar(x) for x in v):
                    body = "[]" if not v else "[" + ", ".join(_dump_scalar(x) for x in v) + "]"
                    out.append(f"{lead}{key}: {body}")
                else:
                    raise YAMLError("nested blocks inside sequence items are not supported")
        else:
            raise YAMLError(f"unsupported sequence item type: {type(item).__name__}")


def dump(obj: dict[str, Any]) -> str:
    out: list[str] = []
    _dump(obj, 0, out)
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _strip_comment(line: str) -> str:
    in_s = in_d = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_d and ch == "\\":
            i += 2
            continue
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
        i += 1
    return line


def _parse_scalar(tok: str) -> Any:
    tok = tok.strip()
    if tok == "" or tok in ("null", "~"):
        return None
    if tok in ("true", "True"):
        return True
    if tok in ("false", "False"):
        return False
    if len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"':
        return tok[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(tok) >= 2 and tok[0] == "'" and tok[-1] == "'":
        return tok[1:-1].replace("''", "'")
    if tok.startswith("[") and tok.endswith("]"):
        return _parse_flow_list(tok[1:-1])
    if tok in ("{}", "[]"):
        return {} if tok == "{}" else []
    if _INT_RE.match(tok):
        return int(tok)
    if _FLOAT_RE.match(tok):
        return float(tok)
    return tok


def _split_flow(body: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    in_s = in_d = False
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if in_d and ch == "\\" and i + 1 < n:
            buf.append(ch)
            buf.append(body[i + 1])
            i += 2
            continue
        if ch == "'" and not in_d:
            in_s = not in_s
            buf.append(ch)
        elif ch == '"' and not in_s:
            in_d = not in_d
            buf.append(ch)
        elif ch == "," and not in_s and not in_d:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf)
    if tail.strip() or parts:
        parts.append(tail)
    return parts


def _parse_flow_list(body: str) -> list[Any]:
    if not body.strip():
        return []
    return [_parse_scalar(p) for p in _split_flow(body)]


class _Lines:
    def __init__(self, text: str) -> None:
        self.rows: list[tuple[int, str]] = []
        for raw in text.splitlines():
            stripped = _strip_comment(raw)
            if not stripped.strip():
                continue
            lead = stripped[: len(stripped) - len(stripped.lstrip())]
            if "\t" in lead:
                raise YAMLError("tabs are not allowed for indentation")
            indent = len(stripped) - len(stripped.lstrip(" "))
            self.rows.append((indent, stripped.strip()))
        self.i = 0

    def peek(self) -> tuple[int, str] | None:
        return self.rows[self.i] if self.i < len(self.rows) else None


def _split_key(content: str) -> tuple[str, str]:
    in_s = in_d = False
    i = 0
    n = len(content)
    while i < n:
        ch = content[i]
        if in_d and ch == "\\":
            i += 2
            continue
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == ":" and not in_s and not in_d:
            if i + 1 >= n or content[i + 1] in " \t":
                return content[:i].strip(), content[i + 1 :].strip()
        i += 1
    raise YAMLError(f"expected 'key: value', got: {content!r}")


def _parse_map(lines: _Lines, indent: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    while True:
        row = lines.peek()
        if row is None or row[0] < indent or row[1].startswith("- "):
            break
        if row[0] > indent:
            raise YAMLError("unexpected indentation in mapping")
        key, rest = _split_key(row[1])
        lines.i += 1
        if rest != "":
            result[key] = _parse_scalar(rest)
            continue
        nxt = lines.peek()
        if nxt is not None and nxt[1].startswith("- ") and nxt[0] >= indent:
            result[key] = _parse_seq(lines, nxt[0])
        elif nxt is not None and nxt[0] > indent:
            result[key] = _parse_map(lines, nxt[0])
        else:
            result[key] = None
    return result


def _parse_seq(lines: _Lines, indent: int) -> list[Any]:
    items: list[Any] = []
    while True:
        row = lines.peek()
        if row is None or row[0] != indent or not row[1].startswith("- "):
            break
        body = row[1][2:].strip()
        lines.i += 1
        if ":" in body and not (body.startswith("[") or body.startswith('"') or body.startswith("'")):
            # inline mapping start: "- key: value" plus following "  key: value"
            item: dict[str, Any] = {}
            key, rest = _split_key(body)
            item[key] = _parse_scalar(rest)
            child_indent = indent + 2
            while True:
                nr = lines.peek()
                if nr is None or nr[0] != child_indent or nr[1].startswith("- "):
                    break
                k2, r2 = _split_key(nr[1])
                item[k2] = _parse_scalar(r2)
                lines.i += 1
            items.append(item)
        else:
            items.append(_parse_scalar(body))
    return items


def load(text: str) -> dict[str, Any]:
    lines = _Lines(text)
    if lines.peek() is None:
        return {}
    first = lines.peek()
    assert first is not None
    if first[1].startswith("- "):
        raise YAMLError("top-level sequences are not supported; use a mapping")
    result = _parse_map(lines, first[0])
    if lines.peek() is not None:
        raise YAMLError("could not parse entire document (check indentation)")
    return result

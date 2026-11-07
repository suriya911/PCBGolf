"""Tiny s-expression reader/writer for KiCad files (netlists, boards, schematics).

Quoted strings come back as `Q` (a str subclass) holding the raw text between
the quotes (escapes untouched) so they are written back byte for byte; bare
atoms are plain str. Writing produces valid but plain formatting -
run `kicad-cli sch upgrade --force` / open+save in KiCad to get canonical layout.
"""
import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')


class Q(str):
    """A string that was quoted in the source file."""



def parse(text):
    stack = [[]]
    for m in _TOKEN.finditer(text):
        lp, rp, quoted, atom = m.groups()
        if lp:
            stack.append([])
        elif rp:
            node = stack.pop()
            stack[-1].append(node)
        elif quoted is not None:
            stack[-1].append(Q(quoted))
        elif atom is not None:
            stack[-1].append(atom)
    return stack[0][0]


def _atom(a):
    if isinstance(a, Q):
        return '"' + a + '"'
    return str(a)


def dumps(node, indent=0):
    if not isinstance(node, list):
        return _atom(node)
    simple = all(not isinstance(c, list) for c in node)
    if simple:
        return "(" + " ".join(_atom(c) for c in node) + ")"
    pad = "\t" * (indent + 1)
    out = "(" + _atom(node[0])
    for c in node[1:]:
        if isinstance(c, list):
            out += "\n" + pad + dumps(c, indent + 1)
        else:
            out += " " + _atom(c)
    return out + "\n" + "\t" * indent + ")"


def find(node, key):
    """Direct children whose head is `key`."""
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]


def first(node, key, default=None):
    r = find(node, key)
    return r[0] if r else default


def value(node, key, default=None):
    r = first(node, key)
    return r[1] if r and len(r) > 1 else default

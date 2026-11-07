"""Tiny s-expression reader for KiCad files (netlists, boards, schematics)."""
import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')


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
            stack[-1].append(quoted.replace('\\"', '"'))
        elif atom is not None:
            stack[-1].append(atom)
    return stack[0][0]


def find(node, key):
    """Direct children whose head is `key`."""
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]


def first(node, key, default=None):
    r = find(node, key)
    return r[0] if r else default


def value(node, key, default=None):
    r = first(node, key)
    return r[1] if r and len(r) > 1 else default

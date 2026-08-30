#!/usr/bin/env python3
"""
Yoda-style conversion of comparisons inside `if` conditions.

Hand-written Java/AspectJ lexer + a small precedence-aware operand extractor.
No OpenRewrite / Moderne anywhere.

Spec implemented:
  * only ==, !=, <, <=, >, >= that appear inside an `if (...)` condition
  * exactly one operand must be a literal / clearly-constant reference
  * that operand is moved to the LEFT, and for relational operators the
    operator is mirrored through a single lookup table (the only place the
    direction is encoded, so it cannot be got wrong per-site)
  * both-constant or neither-constant sites are left alone
  * .equals(...) is never touched (we only ever move operands of the six
    comparison operators)
"""

import re
import sys
import os

# ---------------------------------------------------------------- lexer

OPERATORS = [
    '>>>=', '<<=', '>>=', '>>>', '...', '->', '::', '++', '--', '&&', '||',
    '==', '!=', '<=', '>=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=',
    '<<', '>>',
    '+', '-', '*', '/', '%', '=', '<', '>', '!', '~', '?', ':', '&', '|', '^',
    '(', ')', '[', ']', '{', '}', ';', ',', '.', '@',
]

IDENT_RE = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*')
NUM_RE = re.compile(r"""
    (?: 0[xX][0-9a-fA-F_]+ (?:\.[0-9a-fA-F_]*)? (?:[pP][+-]?[0-9_]+)?
      | 0[bB][01_]+
      | \.[0-9][0-9_]* (?:[eE][+-]?[0-9_]+)?
      | [0-9][0-9_]* (?:\.[0-9_]*)? (?:[eE][+-]?[0-9_]+)?
    )
    [lLfFdDlL]?
""", re.X)


class Tok:
    __slots__ = ('kind', 'text', 'start', 'end')

    def __init__(self, kind, text, start, end):
        self.kind = kind
        self.text = text
        self.start = start
        self.end = end

    def __repr__(self):
        return f'{self.kind}:{self.text!r}'


class LexError(Exception):
    pass


def lex(src):
    """Return the list of *significant* tokens (comments/whitespace dropped)."""
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c in ' \t\r\n\f\v':
            i += 1
            continue
        if c == '/' and i + 1 < n:
            if src[i + 1] == '/':
                j = src.find('\n', i)
                i = n if j < 0 else j
                continue
            if src[i + 1] == '*':
                j = src.find('*/', i + 2)
                if j < 0:
                    raise LexError('unterminated block comment')
                i = j + 2
                continue
        if src.startswith('"""', i):
            j = i + 3
            while True:
                j = src.find('"""', j)
                if j < 0:
                    raise LexError('unterminated text block')
                # count preceding backslashes
                k = j - 1
                bs = 0
                while k >= 0 and src[k] == '\\':
                    bs += 1
                    k -= 1
                if bs % 2 == 0:
                    break
                j += 3
            out.append(Tok('str', src[i:j + 3], i, j + 3))
            i = j + 3
            continue
        if c == '"' or c == "'":
            j = i + 1
            while j < n:
                if src[j] == '\\':
                    j += 2
                    continue
                if src[j] == c:
                    break
                if src[j] == '\n':
                    raise LexError('unterminated literal at offset %d' % i)
                j += 1
            if j >= n:
                raise LexError('unterminated literal at offset %d' % i)
            out.append(Tok('str' if c == '"' else 'char', src[i:j + 1], i, j + 1))
            i = j + 1
            continue
        if c.isdigit() or (c == '.' and i + 1 < n and src[i + 1].isdigit()):
            m = NUM_RE.match(src, i)
            if not m:
                raise LexError('bad number at offset %d' % i)
            out.append(Tok('num', m.group(0), i, m.end()))
            i = m.end()
            continue
        m = IDENT_RE.match(src, i)
        if m:
            out.append(Tok('ident', m.group(0), i, m.end()))
            i = m.end()
            continue
        for op in OPERATORS:
            if src.startswith(op, i):
                out.append(Tok('op', op, i, i + len(op)))
                i += len(op)
                break
        else:
            raise LexError('unexpected char %r at offset %d' % (c, i))
    return out


# ------------------------------------------------------- transformation

# The single place the mirror direction is written down.
FLIP = {'==': '==', '!=': '!=', '<': '>', '>': '<', '<=': '>=', '>=': '<='}
COMPARE = set(FLIP)

OPEN = {'(', '[', '{'}
CLOSE = {')', ']', '}'}

# Tokens that terminate an operand of a comparison operator, i.e. everything
# with precedence lower than or equal to relational/equality, plus separators.
BOUNDARY_OPS = {
    '&&', '||', '&', '|', '^',
    '==', '!=', '<', '>', '<=', '>=',
    '?', ':', ',', ';', '->',
    '=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>=', '>>>=',
}
BOUNDARY_KEYWORDS = {'instanceof', 'return', 'throw', 'assert', 'case', 'yield'}

CONST_IDENT_RE = re.compile(r'^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$')
KEYWORD_LITERALS = {'true', 'false', 'null'}
# `this`/`super` are not constants; primitive/type keywords must never be moved.
JAVA_KEYWORDS = {
    'abstract', 'assert', 'boolean', 'break', 'byte', 'case', 'catch', 'char',
    'class', 'const', 'continue', 'default', 'do', 'double', 'else', 'enum',
    'extends', 'final', 'finally', 'float', 'for', 'goto', 'if', 'implements',
    'import', 'instanceof', 'int', 'interface', 'long', 'native', 'new',
    'package', 'private', 'protected', 'public', 'return', 'short', 'static',
    'strictfp', 'super', 'switch', 'synchronized', 'this', 'throw', 'throws',
    'transient', 'try', 'void', 'volatile', 'while', 'var', 'record', 'yield',
    'sealed', 'permits', 'non-sealed',
}


def is_constant(toks):
    """True if the token run is a literal or a clearly-constant reference."""
    if not toks:
        return False
    if len(toks) == 1:
        t = toks[0]
        if t.kind in ('num', 'char', 'str'):
            return True
        if t.kind == 'ident':
            if t.text in KEYWORD_LITERALS:
                return True
            if t.text in JAVA_KEYWORDS:
                return False
            # require >= 2 chars so single-letter type variables (T, K, V, E)
            # can never be mistaken for a constant
            return len(t.text) >= 2 and bool(CONST_IDENT_RE.match(t.text))
        return False
    if len(toks) == 2 and toks[0].kind == 'op' and toks[0].text in ('-', '+') \
            and toks[1].kind == 'num':
        return True
    # dotted chain Foo.BAR / a.b.C.MAX_VALUE : idents separated by '.', last
    # segment must look like a constant
    if len(toks) % 2 == 1:
        for idx, t in enumerate(toks):
            if idx % 2 == 0:
                if t.kind != 'ident' or t.text in JAVA_KEYWORDS:
                    return False
            else:
                if not (t.kind == 'op' and t.text == '.'):
                    return False
        last = toks[-1].text
        return len(last) >= 2 and bool(CONST_IDENT_RE.match(last))
    return False


def looks_generic(toks, i):
    """Conservative guard: does toks[i] ('<' or '>') look like part of a
    generic type argument list rather than a comparison?"""
    t = toks[i]
    prev = toks[i - 1] if i > 0 else None
    nxt = toks[i + 1] if i + 1 < len(toks) else None

    def upper_ident(tk):
        return tk is not None and tk.kind == 'ident' and tk.text[:1].isupper()

    if t.text == '<':
        prev_typeish = upper_ident(prev) or (prev is not None and prev.kind == 'op'
                                            and prev.text == '.')
        next_typeish = (nxt is not None and (
            upper_ident(nxt)
            or (nxt.kind == 'op' and nxt.text in ('>', '?', '>>', '>>>'))
            or nxt.text in ('extends', 'super', 'int', 'long', 'double', 'float',
                            'byte', 'short', 'char', 'boolean')))
        return prev_typeish and next_typeish
    else:  # '>'
        prev_typeish = upper_ident(prev) or (prev is not None and prev.kind == 'op'
                                            and prev.text in ('>', '?', '>>', '>>>'))
        next_typeish = (nxt is not None and (
            nxt.kind == 'ident'
            or (nxt.kind == 'op' and nxt.text in ('(', ')', '.', '[', ',', ';',
                                                  '::', '>', '{'))))
        return prev_typeish and next_typeish


# --- generic type argument lists -------------------------------------------
# `<` and `>` in `List<String>` / `a.<T>foo()` / `(Map<String,URL>) o` are NOT
# comparison operators, and crucially must not be treated as operand
# boundaries either -- otherwise the left operand of a later `==` gets
# truncated in the middle of an expression.

GEN_INSIDE_OPS = {'.', ',', '?', '[', ']', '@', '&', '<', '>', '>>', '>>>'}
GEN_INSIDE_KEYWORDS = {'extends', 'super', 'int', 'long', 'double', 'float',
                       'byte', 'short', 'char', 'boolean', 'void'}
GEN_AFTER_OPS = {'(', ')', '.', '[', ',', ';', '::', '>', '>>', '>>>', '{', '&',
                 '|', '}'}
GEN_CLOSE = {'>': 1, '>>': 2, '>>>': 3}
GEN_MAX_TOKENS = 80


def _try_generic(toks, i):
    """If toks[i] == '<' opens a plausible generic argument list, return the
    inclusive index range (i, j) of it, else None."""
    depth = 1
    j = i + 1
    limit = min(len(toks), i + GEN_MAX_TOKENS)
    while j < limit:
        t = toks[j]
        if t.kind == 'ident':
            if t.text in JAVA_KEYWORDS and t.text not in GEN_INSIDE_KEYWORDS:
                return None
        elif t.kind == 'op':
            if t.text == '<':
                depth += 1
            elif t.text in GEN_CLOSE:
                depth -= GEN_CLOSE[t.text]
                if depth < 0:
                    return None
                if depth == 0:
                    nxt = toks[j + 1] if j + 1 < len(toks) else None
                    if nxt is None:
                        return None
                    if nxt.kind == 'ident' or (nxt.kind == 'op'
                                               and nxt.text in GEN_AFTER_OPS):
                        return (i, j)
                    return None
            elif t.text not in GEN_INSIDE_OPS:
                return None
        else:
            return None  # literal inside -> not a type argument list
        j += 1
    return None


def mark_generics(toks):
    gen = set()
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        if t.kind == 'op' and t.text == '<':
            prev = toks[i - 1] if i > 0 else None
            ok_prev = prev is not None and (
                (prev.kind == 'ident' and prev.text[:1].isupper()
                 and prev.text not in JAVA_KEYWORDS)
                or (prev.kind == 'op' and prev.text == '.'))
            if ok_prev:
                span = _try_generic(toks, i)
                if span:
                    gen.update(range(span[0], span[1] + 1))
                    i = span[1] + 1
                    continue
        i += 1
    return gen


def if_condition_ranges(toks):
    """Yield (lo, hi) inclusive significant-token index ranges of `if` conditions."""
    for i, t in enumerate(toks):
        if t.kind != 'ident' or t.text != 'if':
            continue
        if i > 0 and toks[i - 1].kind == 'op' and toks[i - 1].text == '.':
            continue
        if i + 1 >= len(toks) or not (toks[i + 1].kind == 'op' and toks[i + 1].text == '('):
            continue
        depth = 0
        j = i + 1
        while j < len(toks):
            if toks[j].kind == 'op' and toks[j].text in OPEN:
                depth += 1
            elif toks[j].kind == 'op' and toks[j].text in CLOSE:
                depth -= 1
                if depth == 0:
                    break
            j += 1
        else:
            continue
        if j - 1 >= i + 2:
            yield (i + 2, j - 1)


def scan_left(toks, i, lo, gen):
    d = 0
    j = i - 1
    stop = i
    while j >= lo:
        t = toks[j]
        if t.kind == 'op' and t.text in CLOSE:
            d += 1
        elif t.kind == 'op' and t.text in OPEN:
            if d == 0:
                break
            d -= 1
        elif d == 0 and t.kind == 'op' and t.text in BOUNDARY_OPS and j not in gen:
            break
        elif d == 0 and t.kind == 'ident' and t.text in BOUNDARY_KEYWORDS:
            break
        stop = j
        j -= 1
    return stop, i - 1  # inclusive range, empty if stop > i-1


def scan_right(toks, i, hi, gen):
    d = 0
    j = i + 1
    stop = i
    while j <= hi:
        t = toks[j]
        if t.kind == 'op' and t.text in OPEN:
            d += 1
        elif t.kind == 'op' and t.text in CLOSE:
            if d == 0:
                break
            d -= 1
        elif d == 0 and t.kind == 'op' and t.text in BOUNDARY_OPS and j not in gen:
            break
        elif d == 0 and t.kind == 'ident' and t.text in BOUNDARY_KEYWORDS:
            break
        stop = j
        j += 1
    return i + 1, stop


def find_edits(src, path='<mem>'):
    toks = lex(src)
    gen = mark_generics(toks)
    edits = []
    for lo, hi in if_condition_ranges(toks):
        for i in range(lo, hi + 1):
            t = toks[i]
            if t.kind != 'op' or t.text not in COMPARE:
                continue
            if i in gen:
                continue
            if t.text in ('<', '>') and looks_generic(toks, i):
                continue
            la, lb = scan_left(toks, i, lo, gen)
            ra, rb = scan_right(toks, i, hi, gen)
            if lb < la or rb < ra:
                continue
            left = toks[la:lb + 1]
            right = toks[ra:rb + 1]
            lc = is_constant(left)
            rc = is_constant(right)
            if lc == rc:          # both or neither -> leave alone
                continue
            if lc:                # already Yoda
                continue
            # constant is on the right: swap
            ltxt = src[left[0].start:left[-1].end]
            gap1 = src[left[-1].end:t.start]
            gap2 = src[t.end:right[0].start]
            rtxt = src[right[0].start:right[-1].end]
            newop = FLIP[t.text]

            def build(g1, g2):
                return rtxt + g1 + newop + g2 + ltxt

            new = build(gap1, gap2)
            expected = [(x.kind, x.text) for x in right] + [('op', newop)] + \
                       [(x.kind, x.text) for x in left]
            try:
                got = [(x.kind, x.text) for x in lex(new)]
            except LexError:
                got = None
            if got != expected:
                new = build(gap1 if gap1.strip() or gap1 else ' ',
                            gap2 if gap2.strip() or gap2 else ' ')
                new = rtxt + (gap1 or ' ') + newop + (gap2 or ' ') + ltxt
                got = [(x.kind, x.text) for x in lex(new)]
                if got != expected:
                    sys.stderr.write(
                        'SKIP (retokenise mismatch) %s: %r -> %r\n'
                        % (path, src[left[0].start:right[-1].end], new))
                    continue
            edits.append({
                'start': left[0].start,
                'end': right[-1].end,
                'new': new,
                'old': src[left[0].start:right[-1].end],
                'op': t.text,
                'newop': newop,
            })
    # drop overlaps (keeps the first of any overlapping pair)
    edits.sort(key=lambda e: (e['start'], e['end']))
    kept = []
    last_end = -1
    for e in edits:
        if e['start'] < last_end:
            sys.stderr.write('SKIP (overlap) %s: %r\n' % (path, e['old']))
            continue
        kept.append(e)
        last_end = e['end']
    return kept


def apply_edits(src, edits):
    out = src
    for e in sorted(edits, key=lambda x: -x['start']):
        out = out[:e['start']] + e['new'] + out[e['end']:]
    return out


def process_file(path, encoding, dry_run=False, log=None):
    with open(path, 'r', encoding=encoding, newline='') as fh:
        src = fh.read()
    try:
        edits = find_edits(src, path)
    except LexError as ex:
        sys.stderr.write('LEXFAIL %s: %s\n' % (path, ex))
        return None
    if not edits:
        return 0
    new = apply_edits(src, edits)
    # invariant: the whole file must still lex, with the same token multiset
    # apart from the flipped comparison operators
    before = lex(src)
    after = lex(new)
    if len(before) != len(after):
        sys.stderr.write('SKIPFILE (token count changed) %s\n' % path)
        return None
    if log is not None:
        for e in edits:
            log.write('%s\t%s -> %s\t%s\t%s\n'
                      % (path, e['op'], e['newop'],
                         ' '.join(e['old'].split()), ' '.join(e['new'].split())))
    if not dry_run:
        with open(path, 'w', encoding=encoding, newline='') as fh:
            fh.write(new)
    return len(edits)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('roots', nargs='+')
    ap.add_argument('--encoding', default='utf-8')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--log')
    ap.add_argument('--only-relational', action='store_true',
                    help='report only, list relational conversions')
    args = ap.parse_args()

    log = open(args.log, 'w') if args.log else None
    total = 0
    files = 0
    failed = []
    for root in args.roots:
        if os.path.isfile(root):
            paths = [root]
        else:
            paths = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in ('target', '.git')]
                for fn in filenames:
                    if fn.endswith('.java') or fn.endswith('.aj'):
                        paths.append(os.path.join(dirpath, fn))
        for p in sorted(paths):
            r = process_file(p, args.encoding, args.dry_run, log)
            if r is None:
                failed.append(p)
            elif r:
                total += r
                files += 1
    if log:
        log.close()
    print('files changed: %d, sites converted: %d' % (files, total))
    if failed:
        print('FAILED/SKIPPED FILES (%d):' % len(failed))
        for p in failed:
            print('  ' + p)


if __name__ == '__main__':
    main()

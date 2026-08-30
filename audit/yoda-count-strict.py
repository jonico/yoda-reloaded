#!/usr/bin/env python3
"""Count Yoda vs non-Yoda equality comparisons inside `if` conditions.

Spec used for the experiment (deliberately narrow so it is unambiguous and
behaviour-preserving):

  * only `==` and `!=`
  * only inside an `if (...)` condition
  * only where exactly one operand is a LITERAL: a number, a char, a string,
    true/false/null
  * Yoda form  = literal on the LEFT
  * relational operators (<, >, <=, >=) are out of scope, because swapping them
    also requires flipping the operator
  * `x.equals("lit")` is out of scope, because `"lit".equals(x)` changes null
    behaviour and is therefore not behaviour-preserving

usage: yoda-count.py <dir>
"""
import re, sys, pathlib

LIT = r'(?:"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)\'|-?\d+(?:\.\d+)?[LlFfDd]?|true|false|null)'
IDENT = r'[A-Za-z_][A-Za-z0-9_.\[\]()]*'
YODA = re.compile(rf'({LIT})\s*(==|!=)\s*({IDENT})')
NONYODA = re.compile(rf'({IDENT})\s*(==|!=)\s*({LIT})')

def conditions(text):
    """Yield the text inside each `if (...)`, brace-matched on parens."""
    for m in re.finditer(r'\bif\s*\(', text):
        i = m.end() - 1
        depth = 0
        for j in range(i, len(text)):
            if text[j] == '(':
                depth += 1
            elif text[j] == ')':
                depth -= 1
                if depth == 0:
                    yield text[i + 1:j]
                    break

def main():
    root = pathlib.Path(sys.argv[1])
    y = n = 0
    detail = []
    for p in sorted(root.rglob("*.java")):
        txt = p.read_text(errors="ignore")
        fy = fn = 0
        for cond in conditions(txt):
            cond = re.sub(r'//.*', '', cond)
            fy += len(YODA.findall(cond))
            fn += len(NONYODA.findall(cond))
        if fy or fn:
            detail.append((str(p.relative_to(root)), fy, fn))
        y += fy; n += fn
    print(f"yoda={y}  non_yoda={n}  total={y+n}")
    for f, a, b in detail:
        print(f"   {f:64s} yoda={a} non_yoda={b}")

if __name__ == "__main__":
    main()

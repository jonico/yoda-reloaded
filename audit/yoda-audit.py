#!/usr/bin/env python3
"""Wider Yoda audit: equality AND relational, literal OR dotted constant."""
import re, sys, pathlib
LIT = r'(?:"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)\'|-?\d+(?:\.\d+)?[LlFfDd]?|true|false|null|[A-Z][A-Za-z0-9_]*\.[a-zA-Z_][A-Za-z0-9_]*|[A-Z][A-Z0-9_]{2,})'
IDENT = r'[A-Za-z_][A-Za-z0-9_.\[\]()]*'
OPS = r'(?:==|!=|<=|>=|<|>)'
YODA = re.compile(rf'(?<![<>=!])({LIT})\s*({OPS})\s*({IDENT})')
NONY = re.compile(rf'({IDENT})\s*({OPS})\s*({LIT})(?![<>=!])')
def conditions(text):
    for m in re.finditer(r'\bif\s*\(', text):
        i = m.end()-1; d = 0
        for j in range(i, len(text)):
            if text[j]=='(': d+=1
            elif text[j]==')':
                d-=1
                if d==0: yield text[i+1:j]; break
def audit(root, exts=('*.java','*.aj')):
    y=n=ifs=0
    for pat in exts:
        for p in pathlib.Path(root).rglob(pat):
            if '/target/' in str(p) or '/.git/' in str(p): continue
            t = p.read_text(errors='ignore')
            for c in conditions(t):
                ifs += 1
                c = re.sub(r'//.*','',c)
                y += len(YODA.findall(c)); n += len(NONY.findall(c))
    return ifs, y, n
for label, root in [(a.split('=')[0], a.split('=')[1]) for a in sys.argv[1:]]:
    ifs, y, n = audit(root)
    print(f"   {label:34s} if_statements={ifs:5d}  already_yoda={y:4d}  to_convert={n:4d}")

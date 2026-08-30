#!/usr/bin/env python3
"""Report every comparison operator found inside an `if` condition and why it
was or was not converted. Used to sanity-check coverage after the fact."""
import sys, os, collections
sys.path.insert(0, '/tmp/probe/yoda-b')
from yoda import (lex, mark_generics, if_condition_ranges, scan_left, scan_right,
                  is_constant, COMPARE, looks_generic, LexError)

def classify(src):
    toks = lex(src)
    gen = mark_generics(toks)
    out = []
    for lo, hi in if_condition_ranges(toks):
        for i in range(lo, hi + 1):
            t = toks[i]
            if t.kind != 'op' or t.text not in COMPARE:
                continue
            if i in gen:
                out.append(('generic-marked', src[toks[max(lo,i-3)].start:toks[min(hi,i+3)].end]))
                continue
            if t.text in ('<', '>') and looks_generic(toks, i):
                out.append(('looks-generic', src[toks[max(lo,i-3)].start:toks[min(hi,i+3)].end]))
                continue
            la, lb = scan_left(toks, i, lo, gen)
            ra, rb = scan_right(toks, i, hi, gen)
            if lb < la or rb < ra:
                out.append(('empty-operand', src[toks[max(lo,i-3)].start:toks[min(hi,i+3)].end]))
                continue
            left, right = toks[la:lb+1], toks[ra:rb+1]
            lc, rc = is_constant(left), is_constant(right)
            span = src[left[0].start:right[-1].end]
            if lc and rc:
                out.append(('both-constant', span))
            elif not lc and not rc:
                out.append(('neither-constant', span))
            elif lc:
                out.append(('already-yoda', span))
            else:
                out.append(('converted', span))
    return out

def main():
    counts = collections.Counter()
    samples = collections.defaultdict(list)
    enc = sys.argv[1]
    for root in sys.argv[2:]:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ('target', '.git')]
            for fn in filenames:
                if not (fn.endswith('.java') or fn.endswith('.aj')):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    src = open(p, encoding=enc, newline='').read()
                    for kind, span in classify(src):
                        counts[kind] += 1
                        if len(samples[kind]) < 400:
                            samples[kind].append(' '.join(span.split()))
                except LexError as e:
                    counts['LEXFAIL'] += 1
                    samples['LEXFAIL'].append('%s: %s' % (p, e))
    for k, v in counts.most_common():
        print('%-18s %6d' % (k, v))
    for k in ('LEXFAIL', 'empty-operand', 'looks-generic', 'generic-marked', 'both-constant'):
        if samples[k]:
            print('\n-- %s (up to 15 samples) --' % k)
            for s in sorted(set(samples[k]))[:15]:
                print('   ' + s)
    print('\n-- neither-constant, most common 25 --')
    for s, c in collections.Counter(samples['neither-constant']).most_common(25):
        print('   %4d  %s' % (c, s[:110]))

main()

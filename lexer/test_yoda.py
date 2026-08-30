#!/usr/bin/env python3
import sys
sys.path.insert(0, '/tmp/probe/yoda-b')
from yoda import find_edits, apply_edits

CASES = [
    # (input, expected output)
    ("if (x == 0) {}", "if (0 == x) {}"),
    ("if (x != null) {}", "if (null != x) {}"),
    ("if (x < 0) {}", "if (0 > x) {}"),
    ("if (x > 0) {}", "if (0 < x) {}"),
    ("if (x <= 5) {}", "if (5 >= x) {}"),
    ("if (x >= 5) {}", "if (5 <= x) {}"),
    ("if (0 == x) {}", "if (0 == x) {}"),                 # already Yoda
    ("if (a == b) {}", "if (a == b) {}"),                 # neither constant
    ("if (0 == 1) {}", "if (0 == 1) {}"),                 # both constant
    ("if (x.equals(\"lit\")) {}", "if (x.equals(\"lit\")) {}"),
    ("if (s == \"lit\") {}", "if (\"lit\" == s) {}"),
    ("if (c == 'a') {}", "if ('a' == c) {}"),
    ("if (x == -1) {}", "if (-1 == x) {}"),
    ("if (x==-1) {}", "if (-1==x) {}"),
    ("if (x == Foo.BAR) {}", "if (Foo.BAR == x) {}"),
    ("if (x == Integer.MAX_VALUE) {}", "if (Integer.MAX_VALUE == x) {}"),
    ("if (x == SOME_CONSTANT) {}", "if (SOME_CONSTANT == x) {}"),
    ("if (x == Status.Active) {}", "if (x == Status.Active) {}"),  # not ALLCAPS
    # compound
    ("if (a > 0 && b.size() != 3) {}", "if (0 < a && 3 != b.size()) {}"),
    ("if (a > 0 || b < MAX) {}", "if (0 < a || MAX > b) {}"),
    # additive / multiplicative operands stay together
    ("if (a + 1 > 0) {}", "if (0 < a + 1) {}"),
    ("if (a * b % 3 == 0) {}", "if (0 == a * b % 3) {}"),
    ("if (x >> 2 == 0) {}", "if (0 == x >> 2) {}"),
    ("if ((flags & MASK) != 0) {}", "if (0 != (flags & MASK)) {}"),
    ("if (flags & MASK != 0) {}", "if (flags & MASK != 0) {}"),  # both const
    # unary
    ("if (!flag == true) {}", "if (true == !flag) {}"),
    ("if (-x < 0) {}", "if (0 > -x) {}"),
    # method call operands
    ("if (foo(a, b) == 0) {}", "if (0 == foo(a, b)) {}"),
    ("if (foo(a == 1, b) ) {}", "if (foo(1 == a, b) ) {}"),
    ("if (list.stream().anyMatch(v -> v == 0)) {}",
     "if (list.stream().anyMatch(v -> 0 == v)) {}"),
    # casts / generics
    ("if (((List<String>) o).size() == 0) {}",
     "if (0 == ((List<String>) o).size()) {}"),
    ("if (((List<URL>) o).size() == 0) {}",
     "if (0 == ((List<URL>) o).size()) {}"),
    ("if (new ArrayList<URL>().size() == 0) {}",
     "if (0 == new ArrayList<URL>().size()) {}"),
    ("if (m instanceof Map<String, URL>) {}", "if (m instanceof Map<String, URL>) {}"),
    ("if (a.<String>foo() == 0) {}", "if (0 == a.<String>foo()) {}"),
    ("if (Collections.<URL>emptyList().size() > 0) {}",
     "if (0 < Collections.<URL>emptyList().size()) {}"),
    # nothing outside if
    ("while (x == 0) {}", "while (x == 0) {}"),
    ("return x == 0;", "return x == 0;"),
    ("assert x == 0;", "assert x == 0;"),
    ("int y = x == 0 ? 1 : 2;", "int y = x == 0 ? 1 : 2;"),
    ("for (int i = 0; i < n; i++) {}", "for (int i = 0; i < n; i++) {}"),
    ("do {} while (x < 0);", "do {} while (x < 0);"),
    # else if
    ("if (a) {} else if (x == 0) {}", "if (a) {} else if (0 == x) {}"),
    # comments and strings must be ignored
    ('if (x == 0) { /* y == 1 */ }', 'if (0 == x) { /* y == 1 */ }'),
    ('String s = "if (x == 0)"; if (y == 1) {}', 'String s = "if (x == 0)"; if (1 == y) {}'),
    ('// if (x == 0)\nif (y == 1) {}', '// if (x == 0)\nif (1 == y) {}'),
    # multiline condition
    ("if (someVeryLongName\n        == 0) {}", "if (0\n        == someVeryLongName) {}"),
    ("if (a\n     && b > 0) {}", "if (a\n     && 0 < b) {}"),
    # ternary inside if condition
    ("if ((a ? b : c) == 0) {}", "if (0 == (a ? b : c)) {}"),
    ("if (a ? b == 1 : c == 2) {}", "if (a ? 1 == b : 2 == c) {}"),
    # text block
    ('if (x == 0) { var t = """\n  y == 1\n  """; }',
     'if (0 == x) { var t = """\n  y == 1\n  """; }'),
    # char literal edge cases
("if (c == '\\'') {}", "if ('\\'' == c) {}"),
    ("if (c == '\\\\') {}", "if ('\\\\' == c) {}"),
    # array / field access non-constant side
    ("if (arr[i] == 0) {}", "if (0 == arr[i]) {}"),
    ("if (arr[IDX] == 0) {}", "if (0 == arr[IDX]) {}"),
    ("if (x == ARR[0]) {}", "if (x == ARR[0]) {}"),   # right not a simple constant
    # nested if inside lambda body inside if condition: outer edit wins, the
    # inner one is dropped as an overlap (known, documented limitation)
    ("if (f(() -> { if (q == 1) { return 2; } return 3; }) == 0) {}",
     "if (0 == f(() -> { if (q == 1) { return 2; } return 3; })) {}"),
    # hex / long / float literals
    ("if (x == 0xFFL) {}", "if (0xFFL == x) {}"),
    ("if (d < 1.5e-3) {}", "if (1.5e-3 > d) {}"),
    ("if (n == 1_000) {}", "if (1_000 == n) {}"),
    # single-letter type var must not count as a constant
    ("if (foo(List<T> a) == 0) {}", "if (0 == foo(List<T> a)) {}"),
    # AspectJ pointcut-ish if()
    ("pointcut p(): execution(* *(..)) && if(x > 0);",
     "pointcut p(): execution(* *(..)) && if(0 < x);"),
    # do not touch == inside a nested annotation-ish / string concat
    ('if (s == "a" + "b") {}', 'if (s == "a" + "b") {}'),
    # negative: keyword operands
    ("if (x == this) {}", "if (x == this) {}"),
    ("if (o == super.get()) {}", "if (o == super.get()) {}"),
]


def run():
    bad = 0
    for src, want in CASES:
        edits = find_edits(src)
        got = apply_edits(src, edits)
        if got != want:
            bad += 1
            print('FAIL')
            print('  in   : %r' % src)
            print('  got  : %r' % got)
            print('  want : %r' % want)
    print('%d/%d cases pass' % (len(CASES) - bad, len(CASES)))
    return bad


if __name__ == '__main__':
    sys.exit(1 if run() else 0)

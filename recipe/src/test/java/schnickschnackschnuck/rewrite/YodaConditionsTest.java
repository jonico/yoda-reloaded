package schnickschnackschnuck.rewrite;

import static org.openrewrite.java.Assertions.java;

import org.junit.jupiter.api.Test;
import org.openrewrite.test.RecipeSpec;
import org.openrewrite.test.RewriteTest;

class YodaConditionsTest implements RewriteTest {

    @Override
    public void defaults(RecipeSpec spec) {
        spec.recipe(new YodaConditions());
    }

    @Test
    void flipsRelationalOperatorWhenSwapping() {
        rewriteRun(
                java(
                        """
                        class A {
                            void m(int x, int n) {
                                if (x < 0) { }
                                if (x <= 0) { }
                                if (x > 0) { }
                                if (x >= 0) { }
                                if (x == 0) { }
                                if (x != 0) { }
                            }
                        }
                        """,
                        """
                        class A {
                            void m(int x, int n) {
                                if (0 > x) { }
                                if (0 >= x) { }
                                if (0 < x) { }
                                if (0 <= x) { }
                                if (0 == x) { }
                                if (0 != x) { }
                            }
                        }
                        """));
    }

    @Test
    void convertsOnlyTheOperandThatHasAConstantInACompoundCondition() {
        rewriteRun(
                java(
                        """
                        import java.util.List;
                        class A {
                            void m(int i, List<String> list) {
                                if (i >= list.size() || i < 0) { }
                                if (i < 0 || i >= list.size()) { }
                            }
                        }
                        """,
                        """
                        import java.util.List;
                        class A {
                            void m(int i, List<String> list) {
                                if (i >= list.size() || 0 > i) { }
                                if (0 > i || i >= list.size()) { }
                            }
                        }
                        """));
    }

    @Test
    void handlesConstantsAndLiteralKinds() {
        rewriteRun(
                java(
                        """
                        class A {
                            static final int LIMIT = 3;
                            void m(int x, char c, String s, boolean b, Object o) {
                                if (x > LIMIT) { }
                                if (x < Integer.MAX_VALUE) { }
                                if (c == 'a') { }
                                if (s == "lit") { }
                                if (b == true) { }
                                if (o != null) { }
                            }
                        }
                        """,
                        """
                        class A {
                            static final int LIMIT = 3;
                            void m(int x, char c, String s, boolean b, Object o) {
                                if (LIMIT < x) { }
                                if (Integer.MAX_VALUE > x) { }
                                if ('a' == c) { }
                                if ("lit" == s) { }
                                if (true == b) { }
                                if (null != o) { }
                            }
                        }
                        """));
    }

    @Test
    void leavesAlreadyYodaAndNonConstantAndBothConstantComparisons() {
        rewriteRun(
                java(
                        """
                        import java.util.List;
                        class A {
                            static final int LO = 1;
                            static final int HI = 2;
                            void m(int x, int y, List<String> list) {
                                if (0 > x) { }
                                if (x < y) { }
                                if (x < list.size()) { }
                                if (LO < HI) { }
                            }
                        }
                        """));
    }

    @Test
    void neverReordersEqualsCalls() {
        rewriteRun(
                java(
                        """
                        class A {
                            void m(String s) {
                                if (s.equals("lit")) { }
                                if (!s.equals("lit")) { }
                            }
                        }
                        """));
    }

    @Test
    void leavesComparisonsOutsideIfConditionsAlone() {
        rewriteRun(
                java(
                        """
                        class A {
                            boolean f(int x) {
                                return x < 0;
                            }
                            void m(int x) {
                                while (x < 0) { x++; }
                                for (int i = 0; i < 10; i++) { }
                                boolean b = x != 0;
                                int y = x > 0 ? 1 : 2;
                            }
                        }
                        """));
    }

    @Test
    void convertsInsideNestedIfsAndElseIfChains() {
        rewriteRun(
                java(
                        """
                        class A {
                            void m(int x, int y) {
                                if (x < 0) {
                                    if (y > 5) { }
                                } else if (x == 7) {
                                    while (y < 3) { y++; }
                                }
                            }
                        }
                        """,
                        """
                        class A {
                            void m(int x, int y) {
                                if (0 > x) {
                                    if (5 < y) { }
                                } else if (7 == x) {
                                    while (y < 3) { y++; }
                                }
                            }
                        }
                        """));
    }

    @Test
    void handlesParenthesesAndNegation() {
        rewriteRun(
                java(
                        """
                        class A {
                            void m(int x, int y) {
                                if (!(x < 0)) { }
                                if ((x < 0) && (y >= 2)) { }
                            }
                        }
                        """,
                        """
                        class A {
                            void m(int x, int y) {
                                if (!(0 > x)) { }
                                if ((0 > x) && (2 <= y)) { }
                            }
                        }
                        """));
    }
}

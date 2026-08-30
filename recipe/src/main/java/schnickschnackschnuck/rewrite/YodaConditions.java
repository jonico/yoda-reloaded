package schnickschnackschnuck.rewrite;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.Expression;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.JLeftPadded;
import org.openrewrite.java.tree.Space;

/**
 * Rewrites comparisons inside {@code if} conditions into Yoda style: the constant goes on the left.
 *
 * <p>The spec this implements is deliberately narrow so that it is unambiguous and
 * behaviour-preserving:
 *
 * <ul>
 *   <li>Applies to {@code ==}, {@code !=}, {@code <}, {@code <=}, {@code >}, {@code >=} <b>inside an
 *       {@code if} condition only</b>. Comparisons in {@code while}, {@code for}, ternaries, return
 *       statements or assignments are left alone.
 *   <li>Applies only where <b>exactly one</b> operand is a literal or a constant: a number, char,
 *       string, {@code true}/{@code false}/{@code null}, or an {@code UPPER_SNAKE_CASE} constant
 *       reference (bare or dotted). If both sides are constant, or neither is, nothing happens.
 *   <li>Relational operators are flipped when the operands are swapped, so {@code x < 0} becomes
 *       {@code 0 > x} and {@code x >= n} becomes {@code n <= x}. {@code ==} and {@code !=} are
 *       symmetric and keep their operator.
 *   <li>{@code x.equals("lit")} is <b>not</b> turned into {@code "lit".equals(x)}. That changes null
 *       behaviour. Method invocations are not {@code J.Binary} nodes, so they are excluded
 *       structurally rather than by a special case.
 * </ul>
 *
 * <p>Nested boolean structure is handled: {@code &&}, {@code ||} and parenthesised sub-expressions
 * are traversed, and each eligible comparison inside them is converted independently. That is what
 * makes a compound condition such as {@code if (i >= list.size() || i < 0)} convert its second
 * operand only, since the first has no constant operand.
 */
public class YodaConditions extends Recipe {

    @Override
    public String getDisplayName() {
        return "Yoda conditions";
    }

    @Override
    public String getDescription() {
        return "Move the constant to the left-hand side of comparisons inside `if` conditions, "
                + "flipping relational operators so that behaviour is preserved. "
                + "Only comparisons with exactly one literal or `UPPER_SNAKE_CASE` constant operand "
                + "are touched, and `equals` calls are never reordered.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {

            @Override
            public J.If visitIf(J.If iff, ExecutionContext ctx) {
                J.If visited = super.visitIf(iff, ctx);
                // Only rewrite within the condition, never the then/else bodies. The bodies were
                // already visited by super (so nested `if`s inside them are handled by their own
                // visitIf call), and rewriting is scoped by rebuilding the condition alone.
                J.ControlParentheses<Expression> cond = visited.getIfCondition();
                Expression rewritten = yodaify(cond.getTree());
                if (rewritten == cond.getTree()) {
                    return visited;
                }
                return visited.withIfCondition(cond.withTree(rewritten));
            }

            /** Recurse through the boolean structure of a condition, converting each comparison. */
            private Expression yodaify(Expression e) {
                if (e instanceof J.Parentheses) {
                    @SuppressWarnings("unchecked")
                    J.Parentheses<Expression> parens = (J.Parentheses<Expression>) e;
                    Expression inner = yodaify(parens.getTree());
                    return inner == parens.getTree() ? parens : parens.withTree(inner);
                }
                if (e instanceof J.Unary) {
                    J.Unary unary = (J.Unary) e;
                    Expression inner = yodaify(unary.getExpression());
                    return inner == unary.getExpression() ? unary : unary.withExpression(inner);
                }
                if (!(e instanceof J.Binary)) {
                    return e;
                }
                J.Binary binary = (J.Binary) e;
                J.Binary.Type op = binary.getOperator();

                if (op == J.Binary.Type.And || op == J.Binary.Type.Or) {
                    Expression left = yodaify(binary.getLeft());
                    Expression right = yodaify(binary.getRight());
                    if (left == binary.getLeft() && right == binary.getRight()) {
                        return binary;
                    }
                    return binary.withLeft(left).withRight(right);
                }

                if (!isComparison(op)) {
                    return binary;
                }
                if (isConstant(binary.getLeft()) || !isConstant(binary.getRight())) {
                    // Already Yoda, or no constant operand, or both sides constant.
                    return binary;
                }
                return swap(binary);
            }

            /**
             * Swap the operands, flipping the operator, and move the whitespace with the slots
             * rather than with the expressions so the result formats like the original.
             */
            private J.Binary swap(J.Binary binary) {
                Expression oldLeft = binary.getLeft();
                Expression oldRight = binary.getRight();
                Space leftSlot = oldLeft.getPrefix();
                Space rightSlot = oldRight.getPrefix();

                JLeftPadded<J.Binary.Type> operator = binary.getPadding().getOperator();

                return binary.getPadding()
                        .withOperator(operator.withElement(flip(operator.getElement())))
                        .withLeft(oldRight.withPrefix(leftSlot))
                        .withRight(oldLeft.withPrefix(rightSlot));
            }

            private boolean isComparison(J.Binary.Type op) {
                return op == J.Binary.Type.Equal
                        || op == J.Binary.Type.NotEqual
                        || op == J.Binary.Type.LessThan
                        || op == J.Binary.Type.LessThanOrEqual
                        || op == J.Binary.Type.GreaterThan
                        || op == J.Binary.Type.GreaterThanOrEqual;
            }

            private J.Binary.Type flip(J.Binary.Type op) {
                switch (op) {
                    case LessThan:
                        return J.Binary.Type.GreaterThan;
                    case GreaterThan:
                        return J.Binary.Type.LessThan;
                    case LessThanOrEqual:
                        return J.Binary.Type.GreaterThanOrEqual;
                    case GreaterThanOrEqual:
                        return J.Binary.Type.LessThanOrEqual;
                    default:
                        // == and != are symmetric.
                        return op;
                }
            }

            /**
             * A literal, or an {@code UPPER_SNAKE_CASE} constant reference, bare (`MAX`) or dotted
             * (`Integer.MAX_VALUE`). Deliberately conservative: anything else, including plain
             * variables, fields and method calls, is not a constant for this recipe's purposes.
             */
            private boolean isConstant(Expression e) {
                if (e instanceof J.Literal) {
                    return true;
                }
                if (e instanceof J.Identifier) {
                    return isConstantName(((J.Identifier) e).getSimpleName());
                }
                if (e instanceof J.FieldAccess) {
                    return isConstantName(((J.FieldAccess) e).getSimpleName());
                }
                return false;
            }

            private boolean isConstantName(String name) {
                if (name.isEmpty()) {
                    return false;
                }
                boolean sawLetter = false;
                for (int i = 0; i < name.length(); i++) {
                    char c = name.charAt(i);
                    if (Character.isUpperCase(c)) {
                        sawLetter = true;
                    } else if (c != '_' && !Character.isDigit(c)) {
                        return false;
                    }
                }
                return sawLetter;
            }
        };
    }
}

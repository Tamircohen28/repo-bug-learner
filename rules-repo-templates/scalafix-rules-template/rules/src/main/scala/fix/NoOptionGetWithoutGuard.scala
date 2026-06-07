/*
 * NoOptionGetWithoutGuard
 *
 * `Option.get` is Scala's NPE — throws NoSuchElementException on None. Most
 * Bookings runtime errors traced via Sentry start here. This rule flags
 * `.get` calls where the receiver is Option[_] and isn't preceded by an
 * isDefined/isEmpty/nonEmpty/exists guard.
 *
 * For provably-safe cases (Option.get inside `if (opt.isDefined)`), the rule
 * is silent. For the rest, it suggests getOrElse, fold, pattern match, or for-yield.
 *
 * Origin bugs:
 *   - SCHED-XXXXX
 *   - SCHED-YYYYY
 *   - SCHED-ZZZZZ
 */
package fix

import scalafix.v1._
import scala.meta._

class NoOptionGetWithoutGuard extends SemanticRule("NoOptionGetWithoutGuard") {

  private val OptionSymbol = Symbol("scala/Option#")

  override def fix(implicit doc: SemanticDocument): Patch = {
    doc.tree.collect {
      case t @ Term.Select(receiver, Term.Name("get"))
          if isOption(receiver) && !isGuarded(t) =>
        Patch.lint(Diagnostic(
          id = "option-get-without-guard",
          message =
            ".get on Option without an isDefined/nonEmpty guard. Use getOrElse, " +
              "fold, pattern match, or for-yield. If you're sure it's defined, " +
              "extract the value via pattern match for clarity.",
          position = t.pos,
          severity = LintSeverity.Error,
        ))
    }.asPatch
  }

  private def isOption(t: Term)(implicit doc: SemanticDocument): Boolean =
    t.symbol.info.exists { info =>
      info.signature match {
        case ValueSignature(TypeRef(_, sym, _)) => sym == OptionSymbol
        case MethodSignature(_, _, TypeRef(_, sym, _)) => sym == OptionSymbol
        case _ => false
      }
    }

  /** True if `t` is inside `if (sameOption.isDefined) ...` or similar guard. */
  private def isGuarded(t: Term.Select): Boolean = {
    val receiverText = t.qual.syntax
    // Walk up the tree; if we find an enclosing if/while whose condition mentions
    // the same receiver and a guard predicate, we treat the .get as guarded.
    var current: Tree = t
    while (current.parent.isDefined) {
      current = current.parent.get
      current match {
        case Term.If(cond, _, _) if isGuardCondition(cond, receiverText) => return true
        case Term.While(cond, _) if isGuardCondition(cond, receiverText) => return true
        case _ =>
      }
    }
    false
  }

  private def isGuardCondition(cond: Term, receiverText: String): Boolean = {
    val text = cond.syntax
    text.contains(s"$receiverText.isDefined") ||
      text.contains(s"$receiverText.nonEmpty") ||
      text.contains(s"!$receiverText.isEmpty")
  }
}

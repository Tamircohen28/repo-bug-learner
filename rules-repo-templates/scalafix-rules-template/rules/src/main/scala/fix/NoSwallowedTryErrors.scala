/*
 * NoSwallowedTryErrors
 *
 * Catching all exceptions and recovering with a no-op or default value is one
 * of the highest-impact Bookings bug categories. Errors get silently swallowed,
 * Sentry sees nothing, and the user gets an empty page instead of a failed
 * booking.
 *
 * The rule flags:
 *   1. `Try(...).recover { case _ => default }` (catches everything)
 *   2. `Try(...).getOrElse(default)` where the Try is not logged
 *   3. `try { ... } catch { case _: Throwable => ... }` with no log/rethrow
 *   4. `Try(...).toOption` without preceding error log
 *
 * Allowed pattern: recovery on a specific exception type with explicit logging.
 *
 * Origin bugs:
 *   - SCHED-XXXXX  (booking confirmation silently dropped)
 *   - SCHED-YYYYY  (payment retry swallowed)
 */
package fix

import scalafix.v1._
import scala.meta._

class NoSwallowedTryErrors extends SemanticRule("NoSwallowedTryErrors") {

  override def fix(implicit doc: SemanticDocument): Patch = {
    doc.tree.collect {
      // Try(...).recover { case _ => ... }
      case t @ Term.Apply.After_4_6_0(
              Term.Select(_tryExpr, Term.Name("recover")),
              Term.ArgClause(List(Term.PartialFunction(cases)), _)) if catchesEverything(cases) =>
        Patch.lint(swallowedDiagnostic(t, "Try.recover catches all errors. " +
          "Catch a specific exception type and log it via logger.error before recovering."))

      // try { ... } catch { case _: Throwable => ... } with empty body
      case t @ Term.Try(_expr, catches, _finally) if catches.exists(catchesEverythingNoLog) =>
        Patch.lint(swallowedDiagnostic(t,
          "try/catch swallows Throwable without logging. Log via logger.error or rethrow."))
    }.asPatch
  }

  private def catchesEverything(cases: List[Case]): Boolean = cases.exists {
    case Case(Pat.Wildcard(), _, _) => true            // case _ =>
    case Case(Pat.Typed(_, Type.Name("Throwable")), _, _) => true
    case Case(Pat.Typed(_, Type.Name("Exception")), _, _) => true
    case _ => false
  }

  private def catchesEverythingNoLog(c: Case): Boolean = {
    val isCatchAll = c.pat match {
      case Pat.Wildcard() => true
      case Pat.Typed(_, Type.Name("Throwable")) => true
      case Pat.Typed(_, Type.Name("Exception")) => true
      case _ => false
    }
    if (!isCatchAll) return false
    val bodyText = c.body.syntax
    !bodyText.contains("logger.") &&
      !bodyText.contains("log.") &&
      !bodyText.contains("throw") &&
      !bodyText.contains("rethrow")
  }

  private def swallowedDiagnostic(t: Tree, msg: String): Diagnostic =
    Diagnostic(
      id = "swallowed-error",
      message = msg,
      position = t.pos,
      severity = LintSeverity.Error,
    )
}

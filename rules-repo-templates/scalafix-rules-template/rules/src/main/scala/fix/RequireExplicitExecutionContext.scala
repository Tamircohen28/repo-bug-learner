/*
 * RequireExplicitExecutionContext
 *
 * Bookings convention: never let Future operations pick up an implicit
 * ExecutionContext from the global scope. Always pass an explicit EC from
 * BookingsExecutionContexts (e.g. dbIO, fastNonBlocking, cpuBound). This
 * prevents:
 *   - Accidentally running blocking DB calls on the global EC (causes pool starvation)
 *   - Accidentally running CPU-heavy work on the IO EC (causes latency spikes)
 *   - Lost stack traces when the wrong EC is used in tests
 *
 * The rule flags any Future.apply / Future.successful / Future.failed / .map /
 * .flatMap / .recover / .recoverWith where the EC argument is implicit (not
 * explicitly named at the call site).
 *
 * Origin bugs:
 *   - SCHED-XXXXX  (DB EC starvation incident)
 *   - SCHED-YYYYY  (latency spike on /api/booking)
 */
package fix

import scalafix.v1._
import scala.meta._

class RequireExplicitExecutionContext extends SemanticRule("RequireExplicitExecutionContext") {

  // Methods that take an implicit ExecutionContext
  private val ecMethods = Set("apply", "map", "flatMap", "filter", "foreach",
                              "recover", "recoverWith", "andThen", "transform",
                              "transformWith", "onComplete", "onSuccess", "onFailure")

  override def fix(implicit doc: SemanticDocument): Patch = {
    doc.tree.collect {
      case t: Term.Apply if needsExplicitEC(t) && !hasExplicitEC(t) =>
        Patch.lint(Diagnostic(
          id = "implicit-execution-context",
          message =
            "Future operation uses implicit ExecutionContext. Bookings convention: " +
              "pass an explicit EC from BookingsExecutionContexts. e.g. " +
              s"`${t.fun.syntax}(...)(BookingsExecutionContexts.dbIO)`.",
          position = t.pos,
          severity = LintSeverity.Error,
        ))
    }.asPatch
  }

  private def needsExplicitEC(t: Term.Apply)(implicit doc: SemanticDocument): Boolean = t.fun match {
    case Term.Select(receiver, Term.Name(method)) if ecMethods(method) =>
      isFutureOrCompanion(receiver)
    case _ => false
  }

  private def isFutureOrCompanion(t: Term)(implicit doc: SemanticDocument): Boolean = {
    val symbolStr = t.symbol.toString
    symbolStr.contains("scala/concurrent/Future") ||
      t.symbol.info.exists { i =>
        i.signature match {
          case ValueSignature(TypeRef(_, sym, _)) => sym.toString.contains("Future")
          case _ => false
        }
      }
  }

  /** True iff the call site has an explicit second argument list with an EC. */
  private def hasExplicitEC(t: Term.Apply): Boolean = {
    // Walk siblings: if the immediate enclosing Term.Apply also passes args
    // (currying), and those args mention an EC, we're good.
    t.parent match {
      case Some(Term.Apply(_, args)) =>
        args.exists { a =>
          val text = a.syntax
          text.contains("ExecutionContext") ||
            text.contains("BookingsExecutionContexts") ||
            text.contains("ec") || text.contains("executor")
        }
      case _ => false
    }
  }
}

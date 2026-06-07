package fix

import scalafix.v1._
import scala.meta._

/**
 * StatusRuntimeExceptionForBusinessError
 *
 * Flags `case class … extends StatusRuntimeException(...)` where the
 * `responseStatus` argument is a non-Internal status such as
 * `ResponseStatus.InvalidArgument`, `FailedPrecondition`, `NotFound`, etc.
 *
 * The recurring bug class is using a system/infrastructure exception base to
 * express a business error. The proper base for those is
 * `ApplicationRuntimeException`, which also carries `applicationDetails`
 * with a stable error code.
 */
class StatusRuntimeExceptionForBusinessError
    extends SyntacticRule("StatusRuntimeExceptionForBusinessError") {

  private val NonInternalStatuses: Set[String] = Set(
    "InvalidArgument",
    "FailedPrecondition",
    "NotFound",
    "AlreadyExists",
    "PermissionDenied",
    "Unauthenticated",
    "OutOfRange",
    "NotImplemented",
    "Unavailable",
    "ResourceExhausted",
    "Aborted",
    "Cancelled",
  )

  override def fix(implicit doc: SyntacticDocument): Patch = {
    doc.tree.collect {
      case init @ Init.After_4_6_0(Type.Name("StatusRuntimeException"), _, argss)
          if hasBusinessStatus(argss.map(_.values)) =>
        Patch.lint(
          Diagnostic(
            id = "business-error-uses-system-exception",
            message =
              "Business-meaning responseStatus on StatusRuntimeException. " +
                "Extend ApplicationRuntimeException with applicationDetails (stable code) instead — " +
                "StatusRuntimeException is for internal/system failures.",
            position = init.pos,
          )
        )
    }.asPatch
  }

  private def hasBusinessStatus(argss: Seq[Seq[Term]]): Boolean =
    argss.flatten.exists {
      case Term.Assign(Term.Name("responseStatus"), rhs) => isBusinessStatus(rhs)
      case t: Term.Select                                => isBusinessStatus(t)
      case _                                             => false
    }

  private def isBusinessStatus(t: Term): Boolean = t match {
    case Term.Select(Term.Name("ResponseStatus"), Term.Name(n)) => NonInternalStatuses.contains(n)
    case Term.Select(_, Term.Name(n))                            => NonInternalStatuses.contains(n)
    case _                                                       => false
  }
}

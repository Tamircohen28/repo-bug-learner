package fix

import scalafix.v1._
import scala.meta._

/**
 * Flags string interpolations of the form `s"... $ident.field ..."` where the
 * `.field` is almost certainly meant to be inside the interpolation (i.e.
 * `${ident.field}`), but is actually being rendered as `<toString of ident> + ".field"`.
 *
 * Real-world bug source (cluster 62, example 4 - bookings-service PR #24533):
 *   s"form submission: $createBookingInfo.formSubmission"
 * should have been:
 *   s"form submission: ${createBookingInfo.formSubmission}"
 *
 * Detection: walk `Lit.String` parts of `Term.Interpolate` looking for parts
 * that begin with `.<identifier>` immediately after a non-braced `${ident}`
 * splice.
 */
class BrokenInterpolationFieldAccess extends SyntacticRule("BrokenInterpolationFieldAccess") {

  // Pattern: a string part starting with ".identifierChars" (the dot suggests
  // an attempted member access that escaped the splice).
  private val LeadingFieldAccess = """^\.[A-Za-z_][A-Za-z0-9_]*""".r

  override def fix(implicit doc: SyntacticDocument): Patch = {
    doc.tree.collect {
      case interp @ Term.Interpolate(Term.Name("s" | "f" | "raw"), parts, args)
          if args.nonEmpty =>
        // parts.size == args.size + 1
        // For each splice arg `args(i)`, the trailing string fragment is `parts(i+1)`.
        // If args(i) is a plain Term.Name (i.e. `$ident`, no braces) AND parts(i+1)
        // starts with ".field", flag it.
        val patches = args.zipWithIndex.collect {
          case (Term.Name(_), i) =>
            val trailing = parts(i + 1) match {
              case Lit.String(v) => v
              case _             => ""
            }
            LeadingFieldAccess.findFirstIn(trailing) match {
              case Some(_) =>
                Patch.lint(
                  Diagnostic(
                    id = "MissingBracesInInterpolation",
                    message =
                      "String interpolation `$" + args(i).syntax + trailing.takeWhile(c => c == '.' || c.isLetterOrDigit || c == '_') +
                        "` likely meant `${" + args(i).syntax + trailing.takeWhile(c => c == '.' || c.isLetterOrDigit || c == '_') + "}`. " +
                        "The `.field` part is rendered literally, not as a member access.",
                    position = args(i).pos,
                  )
                )
              case None => Patch.empty
            }
        }
        patches.asPatch
    }.asPatch
  }
}

package fix

import scalafix.v1._
import scala.meta._

/**
 * MissingDollarInInterpolation
 *
 * Flags `s"..."` / `f"..."` interpolated strings whose textual body contains a
 * bare identifier (e.g. `someVar`) that also exists as a `val` / `var` / `def`
 * / parameter binding *in the same enclosing block*, but is NOT preceded by
 * `$` or `${`. This catches the very common log/email-content bug:
 *
 *     val shouldCustomize = ...
 *     logger.info(..., s"shouldCustomize = shouldCustomize", None)  // BUG
 *
 * where the developer forgot the `$` so the literal name appears in the log
 * instead of the runtime value.
 *
 * This is a syntactic-only heuristic. It deliberately only fires when the
 * referenced identifier is bound in an immediately enclosing `Defn.Def`,
 * `Defn.Val`, `Term.Block`, or `Term.Function` so that false positives are
 * minimised.
 */
class MissingDollarInInterpolation extends SyntacticRule("MissingDollarInInterpolation") {

  private val IdentRegex = "([A-Za-z_][A-Za-z0-9_]*)".r

  override def fix(implicit doc: SyntacticDocument): Patch = {
    doc.tree.collect {
      case interp @ Term.Interpolate(Term.Name(prefix), parts, _)
          if prefix == "s" || prefix == "f" =>
        val bindings = collectEnclosingBindings(interp)
        if (bindings.isEmpty) Patch.empty
        else {
          parts.collect {
            case lit @ Lit.String(value) if containsBareBinding(value, bindings) =>
              Patch.lint(
                Diagnostic(
                  id = "missing-dollar",
                  message =
                    s"Interpolated string contains identifier name(s) " +
                      s"[${barewordsInString(value, bindings).mkString(", ")}] " +
                      s"that match a binding in scope but are not preceded by '$$'. " +
                      s"Did you forget the '$$'?",
                  position = lit.pos
                )
              )
          }.asPatch
        }
    }.asPatch
  }

  /** Walk up parents collecting val/var/def names + parameter names. */
  private def collectEnclosingBindings(t: Tree): Set[String] = {
    val acc = scala.collection.mutable.Set.empty[String]
    var cur: Option[Tree] = t.parent
    while (cur.isDefined) {
      cur.get match {
        case b: Term.Block =>
          b.stats.foreach {
            case Defn.Val(_, pats, _, _) =>
              pats.foreach { case Pat.Var(Term.Name(n)) => acc += n; case _ => () }
            case Defn.Var(_, pats, _, _) =>
              pats.foreach { case Pat.Var(Term.Name(n)) => acc += n; case _ => () }
            case Defn.Def(_, Term.Name(n), _, _, _, _) => acc += n
            case _ => ()
          }
        case d: Defn.Def =>
          d.paramss.flatten.foreach(p => acc += p.name.value)
        case f: Term.Function =>
          f.params.foreach(p => acc += p.name.value)
        case _ => ()
      }
      cur = cur.get.parent
    }
    acc.toSet
  }

  private def barewordsInString(s: String, bindings: Set[String]): List[String] =
    IdentRegex.findAllMatchIn(s).toList.flatMap { m =>
      val name = m.matched
      // Already escaped? Check char before.
      val isInterpolated =
        m.start > 0 && (s.charAt(m.start - 1) == '$' || (m.start > 1 && s
          .substring(m.start - 2, m.start) == "${"))
      if (!isInterpolated && bindings.contains(name)) Some(name) else None
    }

  private def containsBareBinding(s: String, bindings: Set[String]): Boolean =
    barewordsInString(s, bindings).nonEmpty
}

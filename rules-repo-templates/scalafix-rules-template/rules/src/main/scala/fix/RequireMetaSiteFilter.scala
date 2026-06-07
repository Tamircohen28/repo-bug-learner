/*
 * RequireMetaSiteFilter
 *
 * Multi-tenant services must filter collection queries by tenant id or risk
 * cross-tenant data leaks. This rule catches calls to TenantRepo.find* that
 * don't include a tenant filter.
 *
 * Origin bugs:
 *   - PROJ-XXXXX  (replace with real keys after first batch run)
 *
 * This is the canonical example of a SEMANTIC rule: we need to know the
 * receiver's type (TenantRepo specifically, not any repo) and the argument
 * types (whether `tenantId` is among them).
 */
package fix

import scalafix.v1._
import scala.meta._

class RequireMetaSiteFilter extends SemanticRule("RequireMetaSiteFilter") {

  private val TenantRepoSymbol = Symbol("com/example/repo/TenantRepo.")
  private val findMethods = Set("find", "findOne", "findAll", "query", "search")

  override def fix(implicit doc: SemanticDocument): Patch = {
    doc.tree.collect {
      case t @ Term.Apply(Term.Select(receiver, Term.Name(method)), args)
          if findMethods(method) && isTenantRepo(receiver) && !hasTenantFilter(args) =>
        Patch.lint(Diagnostic(
          id = "missing-meta-site-filter",
          message =
            "Query on TenantRepo without tenantId filter is a cross-tenant " +
              "leak risk. Add an explicit tenantId/metaSiteId filter.",
          position = t.pos,
          severity = LintSeverity.Error,
        ))
    }.asPatch
  }

  private def isTenantRepo(receiver: Term)(implicit doc: SemanticDocument): Boolean =
    receiver.symbol.info.exists { sym =>
      sym.signature match {
        case ValueSignature(TypeRef(_, TenantRepoSymbol, _)) => true
        case _                                               => false
      }
    }

  private def hasTenantFilter(args: List[Term]): Boolean = {
    val argText = args.map(_.syntax).mkString(" ")
    argText.contains("metaSiteId") || argText.contains("tenantId")
  }
}

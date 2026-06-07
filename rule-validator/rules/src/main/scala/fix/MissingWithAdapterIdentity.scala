package fix

import scalafix.v1._
import scala.meta._

/** Flags methods in `*Adapter` classes that take an implicit `CallScope`
  * and call an external platformized service via `visibility.exposing { ... }`
  * (or similar) without wrapping the body in `serverSigner.withAdapterIdentity`.
  *
  * Missing this wrapper has caused service-identity leaks across bookings
  * adapters (see PR-29915, which fixed ~19 such methods in one go).
  */
class MissingWithAdapterIdentity extends SyntacticRule("MissingWithAdapterIdentity") {

  override def fix(implicit doc: SyntacticDocument): Patch = {
    doc.tree.collect {
      case cls: Defn.Class if cls.name.value.endsWith("Adapter") =>
        cls.templ.stats.collect {
          case d: Defn.Def if hasImplicitCallScope(d.paramClauseGroups) && needsIdentity(d.body) =>
            Patch.lint(
              Diagnostic(
                id = "MissingWithAdapterIdentity",
                message =
                  s"Adapter method `${d.name.value}` takes an implicit CallScope and calls an external " +
                    s"service but is not wrapped in `serverSigner.withAdapterIdentity { ... }`. " +
                    s"This risks leaking the caller's service identity to downstream services.",
                position = d.name.pos,
              ),
            )
        }
    }.flatten.asPatch
  }

  private def hasImplicitCallScope(groups: List[Member.ParamClauseGroup]): Boolean =
    groups.exists { g =>
      g.paramClauses.exists { pc =>
        pc.mod.exists(_.is[Mod.Implicit]) &&
        pc.values.exists {
          case Term.Param(_, _, Some(t: Type.Name), _) => t.value == "CallScope"
          case _                                       => false
        }
      }
    }

  private def needsIdentity(body: Term): Boolean = {
    // Only `visibility.exposing { block }` is the service-call wrapper. `visibility.expose(event)`
    // is fire-and-forget logging and does not call out to a downstream service.
    val usesExposing = body.collect {
      case Term.Apply(Term.Select(Term.Name("visibility"), Term.Name("exposing")), _) => true
    }.nonEmpty

    // Any of these means the method is signing identity correctly.
    val IdentityMethods = Set(
      "withAdapterIdentity",
      "withServiceIdentity",
      "addServiceIdentity",
      "signWithAdapterIdentity",
    )
    val alreadyWrapped = body.collect {
      case Term.Apply(Term.Select(_, Term.Name(m)), _) if IdentityMethods.contains(m) => true
      case Term.Select(_, Term.Name(m)) if IdentityMethods.contains(m)                => true
    }.nonEmpty

    usesExposing && !alreadyWrapped
  }
}

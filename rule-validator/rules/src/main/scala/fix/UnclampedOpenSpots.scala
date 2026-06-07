package fix

import scalafix.v1._
import scala.meta._

/** UnclampedOpenSpots
  *
  * Flags subtractions of the form `capacity - numberOfParticipants` (or any
  * minuend whose identifier contains `capacity` and subtrahend whose
  * identifier contains `participants`/`registrations`) that are NOT wrapped
  * in `Math.max(_, 0)` / `math.max(_, 0)` and are either:
  *   - assigned to a val whose name contains `openSpots` / `spotsOpen`, or
  *   - passed as the argument to `.withOpenSpots(...)`.
  *
  * Origin: SCHED-21976 / SCHED-35701 in bookings-availability-calendar — the
  * subtraction can go negative when participants > capacity (overbooking,
  * stale snapshots), producing a negative `openSpots` field that downstream
  * consumers treat as "bookable" or fail SQL/UI validators.
  */
class UnclampedOpenSpots extends SyntacticRule("UnclampedOpenSpots") {

  private val CapacityRegex     = "(?i).*capacity.*".r
  private val ParticipantsRegex = "(?i).*(participants|registrations).*".r
  private val OpenSpotsRegex    = "(?i).*(openspots|spotsopen).*".r

  private def isCapacityLike(t: Term): Boolean = t match {
    // capacity.get / capacity.getOrElse(0) — peel BEFORE generic Term.Select arm.
    case Term.Select(inner, Term.Name("get"))                      => isCapacityLike(inner)
    case Term.Apply(Term.Select(inner, Term.Name("getOrElse")), _) => isCapacityLike(inner)
    case Term.Name(n)                                              => CapacityRegex.findFirstIn(n).isDefined
    case Term.Select(_, Term.Name(n))                              => CapacityRegex.findFirstIn(n).isDefined
    case _                                                         => false
  }

  private def isParticipantsLike(t: Term): Boolean = t match {
    case Term.Select(inner, Term.Name("get"))                      => isParticipantsLike(inner)
    case Term.Apply(Term.Select(inner, Term.Name("getOrElse")), _) => isParticipantsLike(inner)
    case Term.Name(n)                                              => ParticipantsRegex.findFirstIn(n).isDefined
    case Term.Select(_, Term.Name(n))                              => ParticipantsRegex.findFirstIn(n).isDefined
    case _                                                         => false
  }

  /** Match `capacity - participants` (capacity-like minus participants-like). */
  private def isOpenSpotsSubtraction(t: Term): Boolean = t match {
    case ai: Term.ApplyInfix
        if ai.op.value == "-" && ai.argClause.values.size == 1 =>
      isCapacityLike(ai.lhs) && isParticipantsLike(ai.argClause.values.head)
    case _ => false
  }

  /** Already clamped: Math.max(expr, 0) or math.max(expr, 0). */
  private def isMaxClamped(t: Term): Boolean = t match {
    case Term.Apply(
          Term.Select(Term.Name("Math") | Term.Name("math"), Term.Name("max")),
          args,
        ) =>
      args.exists(isOpenSpotsSubtraction) &&
        args.exists {
          case Lit.Int(0) => true
          case _          => false
        }
    case _ => false
  }

  override def fix(implicit doc: SyntacticDocument): Patch = {
    doc.tree.collect {
      // Pattern A: val openSpots = capacity - participants
      case d: Defn.Val
          if (d.pats.exists {
                case Pat.Var(Term.Name(n)) => OpenSpotsRegex.findFirstIn(n).isDefined
                case _                     => false
              }) && isOpenSpotsSubtraction(d.rhs) && !isMaxClamped(d.rhs) =>
        val name = d.pats.collectFirst { case Pat.Var(Term.Name(n)) => n }.getOrElse("?")
        Patch.lint(
          Diagnostic(
            id = "unclamped-open-spots",
            message =
              s"`$name` is computed as `capacity - participants` without `Math.max(_, 0)`; " +
                s"this goes negative when participants > capacity. Wrap with `Math.max(..., 0)`.",
            position = d.rhs.pos,
          ),
        )

      // Pattern B: .withOpenSpots(capacity - participants)
      case t @ Term.Apply.After_4_6_0(sel @ Term.Select(_, Term.Name(setter)), Term.ArgClause(List(arg), _))
          if setter.equalsIgnoreCase("withOpenSpots")
            && isOpenSpotsSubtraction(arg)
            && !isMaxClamped(arg) =>
        Patch.lint(
          Diagnostic(
            id = "unclamped-open-spots",
            message =
              s".withOpenSpots(...) receives an unclamped `capacity - participants` subtraction; " +
                s"wrap with `Math.max(..., 0)` to avoid negative open-spot counts.",
            position = sel.name.pos,
          ),
        )
    }.asPatch
  }
}

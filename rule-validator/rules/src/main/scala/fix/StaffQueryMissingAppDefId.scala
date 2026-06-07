package fix

import scalafix.v1._
import scala.meta._

/** StaffQueryMissingAppDefId
  *
  * Flags calls to staff repository / service methods that ENUMERATE staff
  * members (query / list / search / getAll / findAll / fetchAll variants
  * ending in `StaffMember` / `StaffMembers`) without an `appDefId`
  * (or `applicationDefinitionId` / `appId`) scoping argument.
  *
  * Unscoped enumerations have repeatedly caused cross-tenant data leaks and
  * stale-cache bugs in multi-tenant systems (historically 400+ fix PRs
  * across backend and frontend repos).
  *
  * The rule is intentionally narrow: only verbs that signal a multi-row read
  * count. Singleton fetches (`fetchOrCreateDefaultStaffMember`,
  * `getStaffMemberByResourceId`) and mutators
  * (`create*`, `delete*`, `update*`, `assign*`, `disconnect*`, `connect*`,
  * `dispatch*`, `notify*`, `set*`, `add*`, `handle*`) are NOT flagged —
  * they have no filter object on which to attach a scoping field.
  */
class StaffQueryMissingAppDefId
    extends SyntacticRule("StaffQueryMissingAppDefId") {

  private val ReceiverRegex =
    "(?i)^(staffRepository|staffMembersService|staffMembersAdapter|membersRepository|staffApi)$".r

  private val AppDefIdName = "(?i).*(appdefid|applicationdefinitionid|appid)$".r

  // Tightening — only fire on enumerating verbs ending in `StaffMember(s)`.
  // Note: requires `Staff` in the method-name tail so we never match CRM
  // `members.getMembers(...)`-style calls.
  private val EnumeratingStaffMethodRegex =
    "^(query|list|search|getAll|findAll|fetchAll)[A-Za-z]*[Ss]taff[Mm]embers$".r

  // Tightening — explicit blocklist of non-query verbs that must never fire,
  // even if the receiver matches.
  private val NonQueryVerbRegex =
    "^(delete|update|insert|assign|disconnect|connect|create|dispatch|notify|fetchOrCreate|fetch[A-Z]|set[A-Z]|add[A-Z]|handle).*".r

  private def isReceiver(t: Term): Boolean = t match {
    case Term.Name(n)                 => ReceiverRegex.findFirstIn(n).isDefined
    case Term.Select(_, Term.Name(n)) => ReceiverRegex.findFirstIn(n).isDefined
    case _                            => false
  }

  private def isAppDefIdLikeName(s: String): Boolean =
    AppDefIdName.findFirstIn(s).isDefined

  private def argMentionsAppDefId(arg: Term): Boolean = arg match {
    case Term.Assign(Term.Name(n), _) if isAppDefIdLikeName(n)   => true
    case Term.Name(n) if isAppDefIdLikeName(n)                   => true
    case Term.Select(_, Term.Name(n)) if isAppDefIdLikeName(n)   => true
    case _                                                       => false
  }

  override def fix(implicit doc: SyntacticDocument): Patch = {
    doc.tree.collect {
      case app: Term.Apply if isStaffCall(app.fun) =>
        val methodName = methodNameOf(app.fun)
        if (!isFlaggableMethod(methodName)) Patch.empty
        else {
          val args = app.argClause.values
          if (args.exists(argMentionsAppDefId)) Patch.empty
          else
            Patch.lint(
              Diagnostic(
                id = "staff-query-missing-appdefid",
                message =
                  s"Call to staff repo/service `$methodName` is an unbounded " +
                    s"enumeration missing an `appDefId` " +
                    s"(or `applicationDefinitionId`/`appId`) argument. " +
                    s"Unscoped staff queries have caused cross-tenant leaks " +
                    s"and stale-cache bugs. Pass the app-def-id explicitly.",
                position = app.fun.pos,
              ),
            )
        }
    }.asPatch
  }

  // The method must:
  //   - NOT match the non-query verb blocklist
  //   - AND match the enumerating-verb + StaffMembers regex (plural)
  private def isFlaggableMethod(method: String): Boolean = {
    if (NonQueryVerbRegex.findFirstIn(method).isDefined) return false
    EnumeratingStaffMethodRegex.findFirstIn(method).isDefined
  }

  private def isStaffCall(fun: Term): Boolean = fun match {
    case Term.Select(recv, _)                    => isReceiver(recv)
    case Term.ApplyType(Term.Select(recv, _), _) => isReceiver(recv)
    case _                                       => false
  }

  private def methodNameOf(fun: Term): String = fun match {
    case Term.Select(_, Term.Name(m))                    => m
    case Term.ApplyType(Term.Select(_, Term.Name(m)), _) => m
    case _                                               => "<unknown>"
  }
}

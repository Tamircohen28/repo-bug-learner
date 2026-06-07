package fix

import scalafix.v1._
import scala.meta._

/** CalendarNowWithoutExplicitTimezone
  *
  * Flags `DateTime.now()` / `LocalDateTime.now()` / `LocalDate.now()` /
  * `OffsetDateTime.now()` / `ZonedDateTime.now()` calls with NO arguments
  * when the enclosing file looks calendar-/availability-/time-slot-/
  * schedule-related (by class name or file path) AND the resulting value
  * clearly flows into date-range / query semantics rather than being
  * persisted as a storage timestamp.
  *
  * Allowed (skip):
  *   - `<Type>.now(<anything>)`
  *   - `Instant.now()` — Instant is always a UTC instant
  *   - `<Type>.now().getMillis` / `.toInstant` etc. — value collapses to epoch
  *   - file paths under `/test/`, `/contract/`, `/contract-test/`, `/test-kit/`
  *     or files matching `*TestKit.scala`
  *   - files whose enclosing class name contains AppInfo / ServerDynamicConfig
  *     / HealthCheck / Diagnostic (introspection/diagnostic endpoints)
  *   - calls used as the value of a named argument with one of:
  *     `created`, `updatedAt`, `timeStamp`, `dateUpdated`, `lastModified`,
  *     `lastDbAccessTime` (storage-timestamp DTO defaults)
  *
  * Kept firing when the value participates in date-range / query semantics
  * (heuristic: chained `withFromLocalDate(...)`, `LocalDate(...)` constructor
  * wrap, `isAfter(...)`, `plusMonths(...)`, `.toString` chains).
  *
  * Origin: cross-repo signal — calendar-themed PRs (644 in scheduler) consistently
  * fix tz-leak bugs.
  */
class CalendarNowWithoutExplicitTimezone
    extends SyntacticRule("CalendarNowWithoutExplicitTimezone") {

  private val DateTypeNames: Set[String] = Set(
    "DateTime",
    "LocalDateTime",
    "LocalDate",
    "OffsetDateTime",
    "ZonedDateTime",
  )

  private val EpochAccessors: Set[String] = Set(
    "getMillis",
    "getEpochSecond",
    "toEpochMilli",
    "toEpochSecond",
    "toInstant",
  )

  private val CalendarContextRegex =
    "(?i).*(calendar|availability|timeslot|time_slot|schedule|booking).*".r

  // Tightening — skip test / contract / testkit paths entirely.
  private val TestPathRegex =
    "(?i)(/test/|/contract/|/contract-test/|/test-kit/|/testkit/|TestKit\\.scala$|/it/|Spec\\.scala$|Test\\.scala$|TestUtils|TestWrapper|/__tests__/|/__mocks__/)".r

  // Tightening — skip diagnostic / introspection contexts by enclosing class name.
  private val DiagnosticClassRegex =
    "(?i).*(AppInfo|ServerDynamicConfig|HealthCheck|Diagnostic).*".r

  // Tightening — skip when used as value of a storage-timestamp named arg.
  private val StorageTimestampArgNames: Set[String] = Set(
    "created",
    "createdAt",
    "updatedAt",
    "updated",
    "timeStamp",
    "timestamp",
    "dateUpdated",
    "dateCreated",
    "lastModified",
    "lastDbAccessTime",
    "approvalTime",
    "creationTime",
    "transactionTime",
    "registeredAt",
    "completedAt",
    "modifiedAt",
    "insertedAt",
  )

  override def fix(implicit doc: SyntacticDocument): Patch = {
    val path = pathOf(doc)
    if (TestPathRegex.findFirstIn(path).isDefined) return Patch.empty
    if (!isCalendarContext(doc, path)) return Patch.empty
    if (hasDiagnosticClass(doc)) return Patch.empty

    doc.tree.collect {
      case app @ Term.Apply.After_4_6_0(
            Term.Select(Term.Name(typeName), Term.Name("now")),
            argClause,
          )
          if DateTypeNames.contains(typeName) &&
            argClause.values.isEmpty &&
            !isEpochConsumed(app) &&
            !isStorageTimestampNamedArg(app) =>
        Patch.lint(
          Diagnostic(
            id = "calendar-now-without-explicit-timezone",
            message =
              s"`$typeName.now()` is called without an explicit timezone/zone " +
                s"argument in calendar/availability code. This inherits the " +
                s"JVM's default timezone and has caused recurring DST and " +
                s"cross-region bugs. Pass `DateTimeZone.UTC` (Joda) or a " +
                s"`ZoneId` (java.time) explicitly.",
            position = app.pos,
          ),
        )
    }.asPatch
  }

  private def isEpochConsumed(app: Term.Apply): Boolean = app.parent match {
    case Some(Term.Select(`app`, Term.Name(m))) if EpochAccessors.contains(m) =>
      true
    case _ => false
  }

  // Detect: `field = DateTime.now()` where field name suggests storage.
  private def isStorageTimestampNamedArg(app: Term.Apply): Boolean = {
    app.parent match {
      case Some(Term.Assign(Term.Name(n), _))
          if StorageTimestampArgNames.contains(n) =>
        true
      // case-class default arg: `created: DateTime = DateTime.now()`
      case Some(Term.Param(_, Name(n), _, _))
          if StorageTimestampArgNames.contains(n) =>
        true
      // `Some(DateTime.now())` wrapping inside named arg — peek up one more.
      case Some(parent) =>
        parent.parent match {
          case Some(Term.Assign(Term.Name(n), _))
              if StorageTimestampArgNames.contains(n) =>
            // only when intermediate is a simple wrapper Some(...) / Option(...)
            parent match {
              case Term.Apply.After_4_6_0(Term.Name(w), _)
                  if w == "Some" || w == "Option" =>
                true
              case _ => false
            }
          case Some(Term.Param(_, Name(n), _, _))
              if StorageTimestampArgNames.contains(n) =>
            parent match {
              case Term.Apply.After_4_6_0(Term.Name(w), _)
                  if w == "Some" || w == "Option" =>
                true
              case _ => false
            }
          case _ => false
        }
      case _ => false
    }
  }

  private def pathOf(doc: SyntacticDocument): String = doc.input match {
    case scala.meta.Input.File(f, _)        => f.toString
    case scala.meta.Input.VirtualFile(p, _) => p
    case _                                  => ""
  }

  private def isCalendarContext(doc: SyntacticDocument, path: String): Boolean = {
    if (CalendarContextRegex.findFirstIn(path).isDefined) return true
    doc.tree.collect {
      case Defn.Class(_, Type.Name(n), _, _, _)
          if CalendarContextRegex.findFirstIn(n).isDefined => n
      case Defn.Object(_, Term.Name(n), _)
          if CalendarContextRegex.findFirstIn(n).isDefined => n
      case Defn.Trait(_, Type.Name(n), _, _, _)
          if CalendarContextRegex.findFirstIn(n).isDefined => n
    }.nonEmpty
  }

  private def hasDiagnosticClass(doc: SyntacticDocument): Boolean = {
    doc.tree.collect {
      case Defn.Class(_, Type.Name(n), _, _, _)
          if DiagnosticClassRegex.findFirstIn(n).isDefined => n
      case Defn.Object(_, Term.Name(n), _)
          if DiagnosticClassRegex.findFirstIn(n).isDefined => n
      case Defn.Trait(_, Type.Name(n), _, _, _)
          if DiagnosticClassRegex.findFirstIn(n).isDefined => n
    }.nonEmpty
  }
}

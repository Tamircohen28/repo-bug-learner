package fix.test.calendar

// Shims so the fixture compiles without depending on Joda/java.time at the
// classpath level. The rule is purely syntactic; only the names need to match.
object DateTime {
  def now(): DateTime          = new DateTime
  def now(zone: DateTimeZone): DateTime = new DateTime
}
class DateTime {
  def getMillis: Long = 0L
  def plus(ms: Long): DateTime = this
}
object DateTimeZone {
  val UTC: DateTimeZone = new DateTimeZone
}
class DateTimeZone

object Instant {
  def now(): Instant           = new Instant
  def now(clock: Clock): Instant = new Instant
}
class Instant {
  def getEpochSecond: Long = 0L
}
class Clock

object LocalDateTime {
  def now(): LocalDateTime          = new LocalDateTime
  def now(zone: ZoneId): LocalDateTime = new LocalDateTime
}
class LocalDateTime

object LocalDate {
  def now(): LocalDate          = new LocalDate
  def now(zone: ZoneId): LocalDate = new LocalDate
}
class LocalDate

class ZoneId

// GOOD: storage-timestamp case-class default args — must NOT fire.
case class BookingRecord(
  id: String,
  created: DateTime = DateTime.now(),
  updatedAt: DateTime = DateTime.now(),
)

class CalendarAvailabilityService {

  // BAD: bare DateTime.now() in calendar context
  def computeWindowStart(): DateTime =
    DateTime.now() 

  // BAD: bare LocalDateTime.now()
  def computeSlotStart(): LocalDateTime =
    LocalDateTime.now() 

  // BAD: bare LocalDate.now()
  def today(): LocalDate =
    LocalDate.now() 

  // GOOD: Instant.now() — Instant is always UTC, no tz-leak
  def stamp(): Instant =
    Instant.now()

  // GOOD: DateTime.now().getMillis — millis since epoch is tz-agnostic
  def millis(): Long =
    DateTime.now().getMillis

  // GOOD: explicit timezone passed
  def computeWindowStartUtc(): DateTime =
    DateTime.now(DateTimeZone.UTC)

  // GOOD: explicit zone
  def computeSlotStartZoned(z: ZoneId): LocalDateTime =
    LocalDateTime.now(z)

  // GOOD: explicit clock for Instant
  def stampWithClock(c: Clock): Instant =
    Instant.now(c)

  // GOOD: storage-timestamp named arg
  def updateBooking(b: BookingRecord): BookingRecord =
    b.copy(updatedAt = DateTime.now())
}

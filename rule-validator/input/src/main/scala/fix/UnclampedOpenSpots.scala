/*
rule = UnclampedOpenSpots
 */
package fix.test.unclamped

object UnclampedOpenSpotsInput {

  case class Slot(capacity: Option[Int], totalNumberOfParticipants: Int)
  case class Entry(capacity: Option[Int], numberOfRegistrations: Int)

  // ---- positive cases (should flag) ----

  def spotsOpen(slot: Slot): Int = {
    if (slot.capacity.nonEmpty) {
      val openSpots = slot.capacity.get - slot.totalNumberOfParticipants /* assert: UnclampedOpenSpots.unclamped-open-spots*/
      openSpots
    } else 1
  }

  def buildWaitingListItem(entry: Entry): WaitingList = {
    WaitingList()
      .withTotalSpots(entry.capacity.getOrElse(0))
      .withOpenSpots(entry.capacity.getOrElse(0) - entry.numberOfRegistrations) /* assert: UnclampedOpenSpots.unclamped-open-spots*/
  }

  // ---- negative cases (should NOT flag) ----

  def spotsOpenClamped(slot: Slot): Int = {
    if (slot.capacity.nonEmpty) {
      val openSpots = Math.max(slot.capacity.get - slot.totalNumberOfParticipants, 0)
      openSpots
    } else 1
  }

  def spotsOpenClampedMath(slot: Slot): Int = {
    val openSpots = math.max(slot.capacity.getOrElse(0) - slot.totalNumberOfParticipants, 0)
    openSpots
  }

  def unrelatedSubtraction(a: Int, b: Int): Int = a - b

  def unrelatedAssignment(slot: Slot): Int = {
    val remaining = slot.capacity.get - slot.totalNumberOfParticipants
    remaining
  }

  def setterUnrelated(entry: Entry): WaitingList =
    WaitingList().withTotalSpots(entry.capacity.getOrElse(0) - entry.numberOfRegistrations)

  // builder stub
  case class WaitingList(totalSpots: Int = 0, openSpots: Int = 0) {
    def withTotalSpots(n: Int): WaitingList = copy(totalSpots = n)
    def withOpenSpots(n: Int): WaitingList  = copy(openSpots = n)
  }
}

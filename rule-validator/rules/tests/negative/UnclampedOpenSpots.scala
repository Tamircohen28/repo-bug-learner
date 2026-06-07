package com.example.scheduler.tests

object UnclampedOpenSpotsNegatives {
  case class Builder() {
    def withOpenSpots(i: Int): Builder = this
    def withSpotsLeft(i: Int): Builder = this
    def withAvailableSpots(i: Int): Builder = this
  }

  // 1. Math.max clamp
  def case1(capacity: Int, participants: Int): Int = {
    val openSpots = Math.max(capacity - participants, 0)
    openSpots
  }

  // 2. Seq(_, 0).max clamp
  def case2(capacity: Int, participants: Int): Int = {
    val openSpots = Seq(capacity - participants, 0).max
    openSpots
  }

  // 3. math.max (lowercase) clamp
  def case3(maxParticipants: Int, numberOfParticipants: Int): Int = {
    val spotsOpen = math.max(maxParticipants - numberOfParticipants, 0)
    spotsOpen
  }

  // 4. Subtraction outside open-spots context (variable name leftovers)
  def case4(a: Int, b: Int): Int = {
    val delta = a - b
    delta
  }

  // 5. Open-spots-named local but RHS isn't capacity-minus-participants
  def case5(capacity: Int): Int = {
    val openSpots = capacity
    openSpots
  }

  // 6. Non-open-spots variable name with capacity-minus-participants
  def case6(capacity: Int, participants: Int): Int = {
    val leftoverMembers = capacity - participants
    leftoverMembers
  }

  // 7. withOpenSpots wrapped in Math.max
  def case7(capacity: Int, participants: Int, b: Builder): Builder =
    b.withOpenSpots(Math.max(capacity - participants, 0))

  // 8. withSpotsLeft wrapped via math.max
  def case8(maxParticipants: Int, numberOfParticipants: Int, b: Builder): Builder =
    b.withSpotsLeft(math.max(maxParticipants - numberOfParticipants, 0))

  // 9. def using Math.max
  def availableSpots(totalCapacity: Int, numberOfParticipants: Int): Int =
    Math.max(totalCapacity - numberOfParticipants, 0)

  // 10. Unrelated subtraction in arithmetic util
  def percentRemaining(used: Int, total: Int): Int = (total - used) * 100 / total

  // 11. Unrelated domain — money
  def refundOwed(charged: Int, redeemed: Int): Int = charged - redeemed

  // 12. lazy val openSpots clamped
  def case12(capacity: Int, participants: Int): Int = {
    lazy val openSpots: Int = Math.max(capacity - participants, 0)
    openSpots
  }
}

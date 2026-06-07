package com.example.scheduler.tests

// Positive corpus for UnclampedOpenSpots. The SUBTRACT_RE expects `<capName> - <partName>`
// with at most one `.field` after the capacity term — so we use destructured locals.

object UnclampedOpenSpotsPositives {

  def case1(capacity: Int, participants: Int): Int = {
    val openSpots = capacity - participants
    openSpots
  }

  def case2(maxParticipants: Int, numberOfParticipants: Int): Int = {
    var spotsOpen = maxParticipants - numberOfParticipants
    spotsOpen
  }

  def spotsLeft(capacity: Int, participants: Int): Int = capacity - participants

  def case4(totalCapacity: Int, numberOfParticipants: Int): Int = {
    lazy val availableSpots: Int = totalCapacity - numberOfParticipants
    availableSpots
  }

  def remainingCapacity(maxParticipants: Int, participants: Int): Int =
    maxParticipants - participants

  case class Builder() {
    def withOpenSpots(i: Int): Builder = this
    def withSpotsLeft(i: Int): Builder = this
    def withAvailableSpots(i: Int): Builder = this
    def withRemainingCapacity(i: Int): Builder = this
    def withSpotsOpen(i: Int): Builder = this
  }

  def case6(capacity: Int, participants: Int, b: Builder): Builder =
    b.withOpenSpots(capacity - participants)

  def case7(totalCapacity: Int, numberOfParticipants: Int, b: Builder): Builder =
    b.withSpotsLeft(totalCapacity - numberOfParticipants)

  def case8(maxParticipants: Int, numberOfParticipants: Int, b: Builder): Builder =
    b.withAvailableSpots(maxParticipants - numberOfParticipants)

  case class Slot(capacity: Option[Int])
  def case9(slot: Slot, participants: Int): Int = {
    val openSpots = slot.capacity.get - participants
    openSpots
  }

  // SCHED-21976 shape — def returning slot.capacity.get - participants
  def spotsOpen(slot: Slot, participants: Int): Int =
    slot.capacity.get - participants

  def case11(maxCapacity: Int, numberOfParticipants: Int, b: Builder): Builder =
    b.withRemainingCapacity(maxCapacity - numberOfParticipants)

  // lazy val + with* pair
  def case12(capacity: Int, participants: Int): Int = {
    lazy val openSpots: Int = capacity - participants
    openSpots
  }
}

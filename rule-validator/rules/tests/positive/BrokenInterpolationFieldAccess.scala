package com.example.scheduler.tests

// Each positive case: log/exception/throw context with `s"... $ident.field ..."`
// where field is in MEMBER_ACCESSOR_ALLOWLIST.

class BrokenInterpolationFieldAccessPositives {
  private val logger = new {
    def error(msg: String): Unit = println(msg)
    def warn(msg: String): Unit = println(msg)
    def info(msg: String): Unit = println(msg)
  }

  case class Submission(id: String, code: String, status: String, name: String, value: String,
                        message: String, count: Int, total: Int, kind: String, title: String)

  def case1(submission: Submission): Unit = {
    logger.error(s"submitted form $submission.id failed")
  }

  def case2(booking: Submission): Unit = {
    logger.warn(s"booking $booking.code rejected")
  }

  def case3(order: Submission): Unit = {
    throw new RuntimeException(s"order $order.status invalid")
  }

  def case4(svc: Submission): Unit = {
    logger.info(s"service $svc.name notified")
  }

  def case5(req: Submission): Unit = {
    require(req.value.nonEmpty, s"request $req.value must be present")
  }

  def case6(evt: Submission): Unit = {
    logger.error(s"event $evt.message dropped")
  }

  def case7(sess: Submission): Unit = {
    logger.warn(s"session $sess.count too high")
  }

  def case8(slot: Submission): Unit = {
    throw new IllegalStateException(s"slot $slot.total exceeded")
  }

  def case9(payload: Submission): Unit = {
    logger.info(s"payload $payload.kind ignored")
  }

  def case10(record: Submission): Unit = {
    logger.error(s"record $record.title missing")
  }

  def case11(item: Submission): Unit = {
    assert(item.id.nonEmpty, s"item $item.id required")
  }
}

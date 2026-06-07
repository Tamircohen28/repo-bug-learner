package com.example.scheduler.tests

// Each case must have:
// - an s-string with `= <bareIdent>` form
// - <bareIdent> must be a `val/var/def/lazy val` binding in this file
// - <bareIdent> must be interpolated elsewhere ($bareIdent)
// - len(bareIdent) >= 4

object MissingDollarInInterpolationPositives {
  def case1(): Unit = {
    val bookingId = "abc"
    val first = s"booking = bookingId failed"  // should fire
    val ok = s"resolved booking $bookingId"
    println(first + ok)
  }

  def case2(): Unit = {
    val customerName = "alice"
    val m = s"customer = customerName not found"
    val ok = s"customer $customerName logged in"
    println(m + ok)
  }

  def case3(): Unit = {
    val sessionId = "s1"
    val msg = s"event session = sessionId aborted"
    val ok = s"session $sessionId active"
    println(msg + ok)
  }

  def case4(): Unit = {
    val orderId = "o1"
    val log = s"transaction = orderId rejected"
    val ok = s"order $orderId committed"
    println(log + ok)
  }

  def case5(): Unit = {
    val serviceId = "svc"
    val txt = s"linked service = serviceId timeout"
    val ok = s"service $serviceId responded"
    println(txt + ok)
  }

  def case6(): Unit = {
    val scheduleId = "sch1"
    val m = s"target schedule = scheduleId disabled"
    val ok = s"schedule $scheduleId active"
    println(m + ok)
  }

  def case7(): Unit = {
    val resourceId = "r1"
    val r = s"resource = resourceId deleted"
    val ok = s"resource $resourceId reused"
    println(r + ok)
  }

  def case8(): Unit = {
    val staffMemberId = "st1"
    val s = s"member = staffMemberId offline"
    val ok = s"staff $staffMemberId online"
    println(s + ok)
  }

  def case9(): Unit = {
    val tenantId = "t1"
    val msg = s"current tenant = tenantId failed"
    val ok = s"tenant $tenantId loaded"
    println(msg + ok)
  }

  def case10(): Unit = {
    val policyId = "p1"
    val log = s"applied policy = policyId rejected"
    val ok = s"policy $policyId applied"
    println(log + ok)
  }

  def case11(): Unit = {
    val operationName = "op"
    val out = s"operation = operationName failed"
    val ok = s"op $operationName done"
    println(out + ok)
  }
}

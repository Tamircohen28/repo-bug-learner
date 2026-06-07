package com.example.scheduler.tests

object MissingDollarInInterpolationNegatives {
  // 1. Bare ident `login` is a literal label — `login` is NOT a binding here
  def case1(): Unit = {
    val token = "abc"
    val msg = s"action = login for $token"
    println(msg)
  }

  // 2. `submitted` is bound but never interpolated anywhere
  def case2(): Unit = {
    val submitted = "yes"
    val msg = s"state = submitted now"
    println(submitted + msg)
  }

  // 3. The s-string already correctly interpolates the same ident
  def case3(): Unit = {
    val userId = "u1"
    val ok = s"user = $userId logged in"
    val other = s"user $userId session"
    println(ok + other)
  }

  // 4. Ident too short (`tag` = 3 chars)
  def case4(): Unit = {
    val tag = "t1"
    val msg = s"label = tag default"
    val ok = s"tag $tag"
    println(msg + ok)
  }

  // 5. Comparison operator `==` not assignment
  def case5(): Unit = {
    val booking = "x"
    val cmp = s"${if (booking == "x") "yes" else "no"} $booking"
    println(cmp)
  }

  // 6. Right side is a quoted literal, not bare ident
  def case6(): Unit = {
    val userId = "u1"
    val msg = s"action = 'logout' user $userId"
    println(msg)
  }

  // 7. Comparison with `=` inside ${} braces — not a positional `=` pattern
  def case7(): Unit = {
    val status = "ok"
    val msg = s"${status} = active"
    val ok = s"current $status"
    println(msg + ok)
  }

  // 8. Already correctly interpolated as ${ident}
  def case8(): Unit = {
    val customerName = "c"
    val msg = s"name = ${customerName} present"
    val other = s"hi $customerName"
    println(msg + other)
  }

  // 9. RHS uppercase identifier (constants) — BARE_RHS_RE requires leading lowercase
  def case9(): Unit = {
    val Status = "ACTIVE"
    val msg = s"state = STATUS final"
    val ok = s"$Status row"
    println(msg + ok)
  }

  // 10. Bare ident is a Scala keyword-like label, not a binding
  def case10(): Unit = {
    val recipient = "r"
    val msg = s"sent = true to $recipient"
    println(msg)
  }

  // 11. Bare ident only seen as binding; never interpolated. (e.g. label `value`)
  def case11(): Unit = {
    val value = "v"
    val msg = s"output = value here"
    println(value + msg)
  }
}

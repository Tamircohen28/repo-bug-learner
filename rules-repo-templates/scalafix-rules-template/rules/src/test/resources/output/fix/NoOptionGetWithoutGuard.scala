package fix

object NoOptionGetWithoutGuardInput {
  def buggy(maybeBooking: Option[String]): String =
    maybeBooking.get

  def alsoBuggy(maybeUser: Option[Int]): Int = {
    val x = maybeUser.get
    x + 1
  }

  // Safe — guarded by isDefined
  def safe(opt: Option[String]): String =
    if (opt.isDefined) opt.get else "default"

  // Safe — using getOrElse
  def alsoSafe(opt: Option[String]): String = opt.getOrElse("default")
}

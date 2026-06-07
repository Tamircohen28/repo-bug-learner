package fix.test

import scala.concurrent.{ExecutionContext, Future}

class BookingAdapter(
  bookingService: BookingService,
  visibility: Visibility,
  serverSigner: ServiceIdentitySigner,
)(implicit ec: ExecutionContext) {

  // BAD: implicit CallScope + visibility.exposing, no withAdapterIdentity
  def hasFutureBookings(serviceId: String)(implicit callScope: CallScope): Future[Boolean] = 
    visibility.exposing { _ =>
      bookingService.queryExtendedBookings(serviceId).map(_ > 0)
    }(completionEvent = result => None)

  // GOOD: wrapped in withAdapterIdentity
  def listBookings(serviceId: String)(implicit callScope: CallScope): Future[Seq[String]] =
    serverSigner.withAdapterIdentity { implicit cs: CallScope =>
      visibility.exposing { _ =>
        bookingService.list(serviceId)
      }(completionEvent = result => None)
    }

  // GOOD: no implicit CallScope at all
  def helper(x: Int): Int = x + 1

  // GOOD (iter-1 fix): visibility.expose is fire-and-forget logging, not a service-call wrapper.
  // Should NOT fire, even though previously the rule incorrectly treated `expose` like `exposing`.
  def logOnly(x: Int)(implicit callScope: CallScope): Unit =
    visibility.expose("logging only, no downstream call")

  // GOOD (iter-1 fix): addServiceIdentity returns a signed CallScope that gets passed explicitly.
  // This is the alternate identity-signing idiom seen in EventsAdapter/BookingFeesAdapter.
  // Should NOT fire.
  def getEvent(eventId: String)(implicit callScope: CallScope): Future[Boolean] = {
    for {
      signedCallScope <- serverSigner.addServiceIdentity()
      _ <- visibility.exposing { _ =>
        bookingService.queryByEvent(eventId)(signedCallScope)
      }(completionEvent = result => None)
    } yield true
  }
}

class NotAnAdapterClass(visibility: Visibility) {
  // Should NOT fire (class name doesn't end in Adapter)
  def doStuff()(implicit callScope: CallScope): Future[Unit] =
    visibility.exposing { _ => Future.unit }(completionEvent = _ => None)
}

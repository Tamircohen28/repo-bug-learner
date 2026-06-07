// Stub types so that the input source compiles. The synthesized rule is
// purely syntactic — it only inspects names like `visibility.exposing` and
// `serverSigner.withAdapterIdentity` — but scalafix-testkit still requires
// the input project to typecheck (so that SemanticDB can be produced for
// the test harness, even when the rule itself is SyntacticRule).
package fix.test

import scala.concurrent.Future

final class CallScope

trait BookingService {
  def queryExtendedBookings(serviceId: String): Future[Int]
  def queryByEvent(eventId: String)(implicit cs: CallScope): Future[Int]
  def list(serviceId: String): Future[Seq[String]]
}

trait Visibility {
  def exposing[A](f: Any => Future[A])(completionEvent: Future[A] => Option[Any]): Future[A]
  def expose(message: String): Unit
}

trait ServiceIdentitySigner {
  def withAdapterIdentity[A](f: CallScope => Future[A]): Future[A]
  def addServiceIdentity()(implicit cs: CallScope): Future[CallScope]
}


// Stubs for framework error types used by StatusRuntimeExceptionForBusinessError test inputs.
package com.example.framework.errors

sealed trait ResponseStatus
object ResponseStatus {
  case object InvalidArgument    extends ResponseStatus
  case object FailedPrecondition extends ResponseStatus
  case object NotFound           extends ResponseStatus
  case object AlreadyExists      extends ResponseStatus
  case object PermissionDenied   extends ResponseStatus
  case object Unauthenticated    extends ResponseStatus
  case object OutOfRange         extends ResponseStatus
  case object NotImplemented     extends ResponseStatus
  case object Unavailable        extends ResponseStatus
  case object ResourceExhausted  extends ResponseStatus
  case object Aborted            extends ResponseStatus
  case object Cancelled          extends ResponseStatus
  case object Internal           extends ResponseStatus
}

object Details {
  case class ApplicationDetails(code: String, description: Option[String])
}

class StatusRuntimeException(
  message: String = "",
  responseStatus: ResponseStatus = ResponseStatus.Internal,
  responseMessage: String = "",
) extends RuntimeException(message)

class ApplicationRuntimeException(
  responseStatus: ResponseStatus = ResponseStatus.InvalidArgument,
  responseMessage: String = "",
  applicationDetails: Details.ApplicationDetails =
    Details.ApplicationDetails("", None),
) extends RuntimeException(responseMessage)

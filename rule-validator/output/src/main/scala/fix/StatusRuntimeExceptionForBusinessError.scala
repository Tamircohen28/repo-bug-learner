package fix.test.status

import com.example.framework.errors.{
  ApplicationRuntimeException,
  ResponseStatus,
  StatusRuntimeException,
}
import com.example.framework.errors.Details.ApplicationDetails

// Positive: business status on system exception — should warn.
case class InvalidServiceIdsProvided(serviceIds: Seq[String])
    extends StatusRuntimeException(
      message = s"Invalid service ids: ${serviceIds.mkString(",")}",
      responseStatus = ResponseStatus.InvalidArgument,
      responseMessage = s"Invalid service ids: ${serviceIds.mkString(",")}",
    )

// Positive: FailedPrecondition is also a business status — should warn.
case class ResourceSchedulesDoNotExist(resourceIds: Seq[String])
    extends StatusRuntimeException(
      message = s"No schedules for $resourceIds",
      responseStatus = ResponseStatus.FailedPrecondition,
      responseMessage = s"No schedules for $resourceIds",
    )

// Negative: Internal is the correct use of StatusRuntimeException.
case class TrulyInternalFailure(detail: String)
    extends StatusRuntimeException(
      message = detail,
      responseStatus = ResponseStatus.Internal,
      responseMessage = "internal error",
    )

// Negative: already using ApplicationRuntimeException — no warning.
case class InvalidChoicesException()
    extends ApplicationRuntimeException(
      responseStatus = ResponseStatus.InvalidArgument,
      responseMessage = "Invalid choices",
      applicationDetails = ApplicationDetails("INVALID_CHOICES", Some("Invalid choices")),
    )

/*
rule = BrokenInterpolationFieldAccess
 */
package fix.examples

object BrokenInterp {
  case class CreateBookingInfo(formSubmission: String)
  val createBookingInfo = CreateBookingInfo("x")
  val request = "r"

  // Positive: bug from cluster 62 PR #24533
  val bad1 = s"form submission: $createBookingInfo.formSubmission" /* assert: BrokenInterpolationFieldAccess.MissingBracesInInterpolation*/

  // Positive: another shape, trailing field access
  val bad2 = s"req=$request.size end" /* assert: BrokenInterpolationFieldAccess.MissingBracesInInterpolation*/

  // Negative: properly braced
  val good1 = s"form submission: ${createBookingInfo.formSubmission}"

  // Negative: identifier alone, no trailing dot
  val good2 = s"req=$request end"

  // Negative: trailing space/punctuation, not a field
  val good3 = s"req=$request, more"

  // Negative: trailing dot at end of sentence (just punctuation)
  val good4 = s"value is $request."

  // Negative: non-s interpolator that doesn't follow Scala conventions ignored
  val good5 = "no interp here"
}

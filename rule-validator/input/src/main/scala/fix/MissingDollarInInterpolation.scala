/*
rule = MissingDollarInInterpolation
 */
package fix.test

class EmailContentResolver {

  def buggyLog(): String = {
    val shouldCustomizeFooterToDayful = true
    val msg = s"shouldCustomizeFooterParamToDayful = shouldCustomizeFooterToDayful" /* assert: MissingDollarInInterpolation.missing-dollar*/
    msg
  }

  def buggyTwoVars(): String = {
    val firstName = "alice"
    val lastName = "smith"
    s"hello firstName, your surname is lastName" /* assert: MissingDollarInInterpolation.missing-dollar*/
  }

  // Negative: identifier properly interpolated
  def good(): String = {
    val shouldCustomizeFooterToDayful = true
    s"shouldCustomizeFooterParamToDayful = $shouldCustomizeFooterToDayful"
  }

  // Negative: bare word but not a binding in scope
  def noBinding(): String = {
    s"just some random words here"
  }

  // Negative: braces interpolation
  def goodBraces(): String = {
    val name = "x"
    s"hello ${name} world"
  }
}

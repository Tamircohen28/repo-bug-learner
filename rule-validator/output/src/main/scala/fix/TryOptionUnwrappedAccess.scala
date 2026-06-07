/* rule = TryOptionUnwrappedAccess */

import scala.util.Try

object TryOptionUnwrappedAccess {

  // Test 1: Try[List]
  val result: Try[List[Int]] = Try(List(1, 2, 3))
  val size = result.size  // /* assert: size */

  // Test 2: Option[List]
  val option: Option[List[String]] = Some(List("a", "b"))
  val len = option.length  // /* assert: length */

  // Test 3: Properly unwrapped - should NOT trigger
  val wrapped: Try[List[Int]] = Try(List(1, 2, 3))
  val goodSize = wrapped.map(_.size)  // No assert - should not trigger

  // Test 4: Unwrapped with getOrElse - should NOT trigger
  val attempt: Try[Vector[Int]] = Try(Vector(1, 2))
  val safeHead = attempt.getOrElse(Vector()).head  // No assert

  // Test 5: Option with proper unwrapping - should NOT trigger
  val maybeList: Option[List[Int]] = Some(List(1))
  val first = maybeList.map(_.head)  // No assert

  // Test 6: isEmpty is valid on Option - should NOT trigger
  val maybeValue: Option[Int] = Some(42)
  if (maybeValue.isEmpty) {  // No assert - isEmpty is valid
    println("empty")
  }

  // Test 7: Direct Try.size call without unwrapping
  def getTry: Try[List[Int]] = Try(List(1, 2, 3))
  val count = getTry.length  // /* assert: length */

}

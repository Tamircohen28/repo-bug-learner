// Negative corpus: correct Try/Option handling or false positive cases

import scala.util.Try
import scala.collection.immutable.List

// 1. Properly unwrapped with .map
def n1() = {
  val result = Try(List(1, 2, 3))
  println(result.map(_.size).getOrElse(0))
}

// 2. Unwrapped with .fold
def n2() = {
  val option = Some(List(4, 5, 6))
  option.fold(0)(_.length)
}

// 3. Unwrapped with .getOrElse
def n3() = {
  val attempt = Try(Vector(7, 8))
  attempt.getOrElse(Vector()).head
}

// 4. Unwrapped with .flatMap
def n4() = {
  val tryData = Try(List(10, 20, 30))
  tryData.flatMap(d => Try(d.size))
}

// 5. Unwrapped with explicit .get
def n5() = {
  val maybeList = Some(List(1))
  maybeList.get.tail
}

// 6. Variable name has "option" but is a direct List
def n6() = {
  val optionList = List("a", "b")  // Not an Option, just a List with "option" in name
  optionList.isEmpty
}

// 7. Variable with "result" in name but is a concrete collection
def n7() = {
  val myResultSet: java.util.HashSet[Int] = new java.util.HashSet()
  myResultSet.size()  // Java Set, not a Try/Option
}

// 8. Try-like name but it's a wrapper class, not Try
class MyTryWrapper(val items: List[Int]) {
  def size = items.size  // accessing size on the member, not the wrapper
}

def n8() = {
  val tryWrapper = new MyTryWrapper(List(1, 2))
  tryWrapper.size
}

// 9. Unwrapped with .foreach
def n9() = {
  val result = Try(List(1, 2, 3))
  result.foreach(_.size)
}

// 10. Using .recover before accessing
def n10() = {
  val attempt = Try(Vector(1, 2))
  attempt.recover { case _ => Vector(0) }.head
}

// 11. Unwrapped with pattern match
def n11() = {
  val option = Some(List(1, 2))
  option match {
    case Some(list) => list.size
    case None => 0
  }
}

// 12. Using .tap (which returns the Try itself but allows side effects)
def n12() = {
  val result = Try(List(1, 2))
  result.tap(list => println("data: " + list)).map(_.size)
}

// 13. False positive: "attempt" variable that's not a Try
def n13() = {
  val attemptCounter = 5
  attemptCounter.max(10)  // max on Int, not a Try
}

// 14. Accessing methods on a Try itself (not its contents)
def n14() = {
  val result = Try(List(1, 2))
  result.isSuccess  // calling method on Try itself, not on contents
}

// 15. Correct use of .isEmpty on Option (it's a valid method)
def n15() = {
  val maybeList = Some(List(1, 2))
  if (maybeList.isEmpty) {  // Option.isEmpty is correct
    println("empty")
  }
}

// 16. Correct use of .nonEmpty on Try (it's a valid method)
def n16() = {
  val result = Try(List(1, 2, 3))
  if (result.nonEmpty) {  // Try.nonEmpty is correct
    println("has value")
  }
}

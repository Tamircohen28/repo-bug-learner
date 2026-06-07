// Positive corpus: calling collection methods on Try/Option without unwrapping

import scala.util.Try
import scala.collection.immutable.List

def f1() = {
  val result = Try(List(1, 2, 3))
  // ruleid: TryOptionUnwrappedAccess
  println(result.size)
}

def f2() = {
  val option = Some(List(4, 5, 6))
  // ruleid: TryOptionUnwrappedAccess
  val len = option.length
}

def f3() = {
  val attempt = Try(Vector(7, 8))
  // ruleid: TryOptionUnwrappedAccess
  return attempt.head
}

def f4() = {
  val maybeList = Some(List(1))
  // ruleid: TryOptionUnwrappedAccess
  maybeList.tail
}

def f5() = {
  val optValues = Some(Seq(1, 2, 3, 4))
  // ruleid: TryOptionUnwrappedAccess
  optValues.length
}

def f6() = {
  val result = Try(List("a", "b"))
  // ruleid: TryOptionUnwrappedAccess
  val firstElem = result.head
}

def f7() = {
  val trySeq = Try(Seq(1, 2, 3, 4))
  // ruleid: TryOptionUnwrappedAccess
  print(trySeq.size)
}

def f8() = {
  val result = Try(Map("key" -> "value"))
  // ruleid: TryOptionUnwrappedAccess
  println(result.size)
}

def f9() = {
  def getTryList: Try[List[Int]] = Try(List(1, 2, 3))
  val myTry = getTryList
  // ruleid: TryOptionUnwrappedAccess
  val count = myTry.length
}

def f10() = {
  val optOpt = Some(Some(List(5)))
  // ruleid: TryOptionUnwrappedAccess
  optOpt.flatten.size
}

def f11() = {
  val tryList: Try[List[String]] = Try(List("x", "y"))
  // ruleid: TryOptionUnwrappedAccess
  return tryList.last
}

def f12() = {
  val resultSeq = Some(Seq(1, 2))
  // ruleid: TryOptionUnwrappedAccess
  val first = resultSeq.head
}

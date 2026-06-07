// Stub types to allow test input to compile.
// These stubs INTENTIONALLY add invalid methods to Try/Option
// so the input code can compile but will be flagged by the semantic rule.
package scala.util

// Override Try with methods it shouldn't have (for testing)
class Try[+T] private () {
  // Real methods
  def map[U](f: T => U): Try[U] = ???
  def flatMap[U](f: T => Try[U]): Try[U] = ???
  def fold[U](f: Throwable => U, f2: T => U): U = ???
  def getOrElse[U >: T](default: U): U = ???
  def get: T = ???
  def recover[U >: T](f: PartialFunction[Throwable, U]): Try[U] = ???
  def tap(f: Try[T] => Unit): Try[T] = ???
  def foreach(f: T => Unit): Unit = ???

  // INVALID methods (for testing - these are flagged by the rule)
  def size: Int = ???           // Should not exist
  def length: Int = ???         // Should not exist
  def head: T = ???             // Should not exist
  def tail: Try[T] = ???        // Should not exist
  def last: T = ???             // Should not exist
  def init: Try[T] = ???        // Should not exist

  // VALID methods (shouldn't be flagged)
  def isEmpty: Boolean = ???
  def nonEmpty: Boolean = ???
}

object Try {
  def apply[T](r: => T): Try[T] = ???
}

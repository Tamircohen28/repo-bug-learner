// Stub types to allow test input to compile.
// These stubs INTENTIONALLY add invalid methods to Option
// so the input code can compile but will be flagged by the semantic rule.
package scala

// Override Option with methods it shouldn't have (for testing)
sealed trait Option[+A] {
  // Real methods
  def map[B](f: A => B): Option[B] = ???
  def flatMap[B](f: A => Option[B]): Option[B] = ???
  def fold[B](ifEmpty: => B)(f: A => B): B = ???
  def getOrElse[B >: A](default: => B): B = ???
  def get: A = ???
  def recover[B >: A](f: PartialFunction[Throwable, B]): Option[B] = ???
  def tap(f: Option[A] => Unit): Option[A] = ???
  def foreach(f: A => Unit): Unit = ???

  // INVALID methods (for testing - these are flagged by the rule)
  def size: Int = ???           // Should not exist
  def length: Int = ???         // Should not exist
  def head: A = ???             // Should not exist
  def tail: Option[A] = ???     // Should not exist
  def last: A = ???             // Should not exist
  def init: Option[A] = ???     // Should not exist

  // VALID methods (shouldn't be flagged)
  def isEmpty: Boolean = ???
  def nonEmpty: Boolean = ???
}

final case class Some[+A](value: A) extends Option[A]
case object None extends Option[Nothing]

object Option {
  def apply[A](value: A): Option[A] = ???
}

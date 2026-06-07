package fix

import scalafix.v1._
import scala.meta._

/** TryOptionUnwrappedAccess (Semantic Rule)
  *
  * Flags calls to collection/accessor methods (`.size`, `.length`, `.head`, `.tail`, `.last`, `.init`)
  * on variables with actual Try or Option types WITHOUT unwrapping.
  *
  * This is the semantic version that uses type information to eliminate false positives.
  * Unlike the heuristic regex version, this checks the ACTUAL type of the variable,
  * not just its naming pattern.
  *
  * Try/Option don't have: .size, .length, .head, .tail, .last, .init
  * So these methods require unwrapping first: .map(_.method), .fold(..., _.method), .getOrElse, etc.
  *
  * Allowed (skipped):
  *   - Variables that are NOT Try or Option (e.g., Seq, List, Map)
  *   - Calls already unwrapped (.map, .flatMap, .fold, .getOrElse, .recover, etc.)
  *   - Methods like .isEmpty, .nonEmpty (these exist on Try/Option and return Boolean)
  */
class TryOptionUnwrappedAccess extends SemanticRule("TryOptionUnwrappedAccess") {

  private val CollectionMethods: Set[String] = Set(
    "size",
    "length",
    "head",
    "tail",
    "last",
    "init",
  )

  private val UnwrappingMethods: Set[String] = Set(
    "map",
    "flatMap",
    "fold",
    "getOrElse",
    "get",
    "recover",
    "tap",
    "foreach",
  )

  override def fix(implicit doc: SemanticDocument): Patch = {
    doc.tree.collect {
      case select @ Term.Select(receiver, Term.Name(method))
          if CollectionMethods.contains(method) && isTryOrOption(receiver)(doc) =>

        val receiverStr = receiver.toString()
        Patch.lint(
          Diagnostic(
            id = "TryOptionUnwrappedAccess",
            message = s"Calling `.$method` on `$receiverStr` without unwrapping. " +
              s"Try/Option don't have `.$method` — use `.map(_.${method})`, " +
              s"`.fold(..., _.${method})`, or `.getOrElse` to unwrap first.",
            position = select.pos,
          )
        )
    }.asPatch
  }

  /** Check if a term has Try or Option type */
  private def isTryOrOption(term: Term)(implicit doc: SemanticDocument): Boolean = {
    try {
      val symbol = term.symbol
      if (symbol.isNone) return false

      val info = symbol.info
      if (info.isEmpty) return false

      val signature = info.get.signature.toString()

      // Check if type signature contains Try or Option
      signature.contains("scala.util.Try") ||
      signature.contains("scala.Option") ||
      signature.contains("Try[") ||
      signature.contains("Option[")
    } catch {
      case _: Exception => false
    }
  }

  /** Check if term is already within an unwrapping context */
  private def isUnwrapped(term: Term)(implicit doc: SemanticDocument): Boolean = {
    // Walk up the tree to find if we're inside a .map, .flatMap, .fold, etc.
    // This is a simplified check; a full implementation would need better parent tracking
    false  // For now, assume nothing is pre-unwrapped; let semantic analysis catch it
  }
}

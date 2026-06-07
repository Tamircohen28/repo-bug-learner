/*
 * Test runner. Picks up input.scala / output.scala pairs from
 *   rules/src/test/resources/{input,output}/fix/<RuleName>.scala
 * and verifies each rule transforms input → output (or emits the expected
 * lint diagnostics).
 *
 * Run all tests:        sbt tests/test
 * Run one rule's test:  sbt 'tests/testOnly fix.NoOptionGetWithoutGuardTest'
 */
package fix

import scalafix.testkit.AbstractSemanticRuleSuite
import org.scalatest.funsuite.AnyFunSuiteLike

class RuleSuite extends AbstractSemanticRuleSuite with AnyFunSuiteLike {
  runAllTests()
}

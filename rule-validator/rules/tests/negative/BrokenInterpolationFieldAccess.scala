package com.example.scheduler.tests

class BrokenInterpolationFieldAccessNegatives {
  private val logger = new {
    def error(msg: String): Unit = println(msg)
    def info(msg: String): Unit = println(msg)
  }

  // 1. File-extension concat (NOT in log/exception context — path builder)
  def case1(name: String): String = s"$name.json"

  // 2. File-extension concat — yaml
  def case2(prefix: String): String = s"$prefix.yaml"

  // 3. Metric-key concat — outside log context
  def case3(method: String): String = s"$method.error"

  // 4. Properly braced — `${obj.field}`
  def case4(submission: { def id: String }): Unit = {
    logger.error(s"submitted form ${submission.id} failed")
  }

  // 5. Suffix not in allowlist (e.g. `.json` is an extension, not member name)
  def case5(file: String): Unit = {
    logger.info(s"reading file $file.json now")
  }

  // 6. Suffix not in allowlist (`.html`)
  def case6(template: String): Unit = {
    logger.info(s"rendering template $template.html")
  }

  // 7. Path builder outside log context — totally OK
  def buildPath(base: String, file: String): String = s"$base.$file"

  // 8. Outside log context — string concat for URL
  def url(domain: String): String = s"https://$domain.com/api"

  // 9. Metric/key builder — outside log context
  def metricKey(prefix: String): String = s"$prefix.latency.p99"

  // 10. Suffix `.scala` — not allowlist
  def case10(cls: String): Unit = {
    logger.info(s"compiling $cls.scala soon")
  }

  // 11. Plain string with no $ — not an interpolation
  def case11(): Unit = {
    logger.error("submitted form failed")
  }

  // 12. f-string with formatting — but suffix .toml is not allowlist
  def case12(config: String): Unit = {
    logger.info(s"config file $config.toml loaded")
  }
}

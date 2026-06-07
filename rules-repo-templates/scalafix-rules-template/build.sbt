/*
 * static-analysis-scalafix-rules
 *
 * Custom Scalafix rules synthesized from historical bug-fix commits.
 * Generated and maintained by repo-bug-learner.
 *
 * Layout:
 *   rules/        — the rule sources (one .scala file per rule)
 *   tests/        — input/output test fixtures + scalafix-testkit driver
 *   docs/         — auto-generated rule catalog
 */

inThisBuild(List(
  organization := "com.example",
  scalaVersion := "2.12.21",
  version      := "0.1.0-SNAPSHOT",
  publishMavenStyle := true,
))

lazy val V = _root_.scalafix.sbt.BuildInfo

lazy val rules = (project in file("rules"))
  .settings(
    name := "static-analysis-scalafix-rules",
    libraryDependencies ++= Seq(
      "ch.epfl.scala" %% "scalafix-core" % V.scalafixVersion,
    ),
  )

lazy val input = (project in file("input"))
  .settings(
    publish / skip := true,
    // SemanticDB output for the input project, consumed by tests
    semanticdbEnabled := true,
    semanticdbVersion := scalafixSemanticdb.revision,
    scalacOptions ++= Seq("-Yrangepos", "-P:semanticdb:synthetics:on"),
  )

lazy val output = (project in file("output"))
  .settings(
    publish / skip := true,
  )

lazy val tests = (project in file("tests"))
  .settings(
    publish / skip := true,
    libraryDependencies += "ch.epfl.scala" %% "scalafix-testkit" % V.scalafixVersion % Test cross CrossVersion.full,
    Compile / compile := (Compile / compile).dependsOn(input / Compile / compile).value,
    scalafixTestkitOutputSourceDirectories := (output / Compile / sourceDirectories).value,
    scalafixTestkitInputSourceDirectories  := (input / Compile / sourceDirectories).value,
    scalafixTestkitInputClasspath          := (input / Compile / fullClasspath).value,
    scalafixTestkitInputScalacOptions      := (input / Compile / scalacOptions).value,
    scalafixTestkitInputScalaVersion       := (input / Compile / scalaVersion).value,
  )
  .dependsOn(rules)
  .enablePlugins(ScalafixTestkitPlugin)

addCommandAlias("ci", "; tests/test ; rules/publishLocal")

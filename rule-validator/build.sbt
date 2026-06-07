// Validator project for synthesized Scalafix rules (repo-bug-learner stage 5).
//
// Layout follows the standard scalafix-testkit template:
//   rules/  -> rule sources (the synthesized Rule.scala lives here)
//   input/  -> test inputs annotated with `/* rule = ... */` and `/* assert: ... */`
//   output/ -> expected outputs after the rule has been applied
//   tests/  -> the testkit runner that diffs (rule applied to input) vs output

inThisBuild(
  List(
    scalaVersion := "2.13.15",
    semanticdbEnabled := true,
    semanticdbVersion := scalafixSemanticdb.revision,
  )
)

val scalafixV = _root_.scalafix.sbt.BuildInfo.scalafixVersion

lazy val rules = (project in file("rules"))
  .settings(
    libraryDependencies += "ch.epfl.scala" %% "scalafix-core" % scalafixV
  )

lazy val input = (project in file("input"))
  .settings(
    scalacOptions ++= Seq("-Yrangepos"),
    // Stub types needed for the input to typecheck live in `scala-stubs/`.
    // They are compiled into the classpath but NOT registered as
    // scalafix-testkit input sources (only `scala/` is — see `tests` below).
    Compile / unmanagedSourceDirectories +=
      (Compile / sourceDirectory).value / "scala-stubs"
  )

lazy val output = (project in file("output"))
  .settings(
    scalacOptions ++= Seq("-Yrangepos")
  )

lazy val tests = (project in file("tests"))
  .settings(
    libraryDependencies += "ch.epfl.scala" %% "scalafix-testkit" % scalafixV % Test cross CrossVersion.full,
    scalafixTestkitOutputSourceDirectories :=
      (output / Compile / unmanagedSourceDirectories).value,
    // Only the `scala/` dir holds testkit inputs; `scala-stubs/` is excluded.
    scalafixTestkitInputSourceDirectories := Seq(
      (input / Compile / sourceDirectory).value / "scala"
    ),
    scalafixTestkitInputClasspath :=
      (input / Compile / fullClasspath).value,
    scalafixTestkitInputScalacOptions :=
      (input / Compile / scalacOptions).value,
    scalafixTestkitInputScalaVersion :=
      (input / Compile / scalaVersion).value,
  )
  .dependsOn(rules)
  .enablePlugins(ScalafixTestkitPlugin)

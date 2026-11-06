# ADR 001: Scalafix over Opengrep for Scala

## Status

Accepted

## Context

Scala bug patterns often need type and symbol information (Options, Futures, implicits). Opengrep matches syntax only.

## Decision

Route Scala-dominant clusters to Scalafix `SemanticRule` synthesis. Route TS/JS/Python/Go clusters to Opengrep YAML.

## Consequences

- Scala services need SemanticDB in CI (`service-integration/build.sbt.snippet`)
- Opengrep covers all non-Scala languages uniformly

---

<p align="center"><a href="https://github.com/Tamircohen28">Have a Question?</a>&nbsp;·&nbsp;<a href="https://github.com/Tamircohen28/repo-bug-learner/issues/new/choose">Open an Issue</a></p>

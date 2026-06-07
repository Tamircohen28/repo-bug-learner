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

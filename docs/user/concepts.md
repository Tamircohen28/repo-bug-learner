# Concepts

**repo-bug-learner** turns historical bug-fix data into static-analysis rules.

1. **Mine** — closed Jira bugs linked to merged GitHub PRs
2. **Corpus** — buggy code blocks + fix diffs labeled via SZZ
3. **Cluster** — embed and group similar bugs (pgvector + HDBSCAN)
4. **Synthesize** — Claude generates Scalafix (Scala) or Opengrep (TS/JS/Python/Go) rules
5. **Validate** — measure precision/recall on held-out corpus
6. **Ship** — open PRs to your rules repository for human review

Rules from the rules repo gate target repositories via CI workflows in `service-integration/`.

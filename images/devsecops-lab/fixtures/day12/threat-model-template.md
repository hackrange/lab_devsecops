# Threat model: secure-build-lab

- Version of this model: 1 (date: YYYY-MM-DD)
- Scope: the greet service, its repository, its pipeline, and its release artifact
- Participants: (names or roles)
- Standards referenced: OWASP ASVS 5.0.0

## 1. What are we working on?

Paste or draw the data-flow diagram here (text is fine).  Name every
external entity, process, data store, data flow, and trust boundary.

```
[Browser] --HTTP GET /greet--> (greet service) ...
```

## 2. What can go wrong?  (abuse cases)

Each abuse case: who the attacker is, what they do, what they gain, then
prevention, detection, recovery, and the residual risk you accept.

### AC-1: Malicious pull request
- Attacker and goal: an outside contributor wants to run code in our CI
  or slip a backdoor into main.
- How: opens a PR that changes a workflow file, a test, or a build script.
- Prevention: PRs from forks get no secrets and a read-only token; CODEOWNERS
  on .github/workflows/; required review; branch protection with no bypass.
- Detection: required status checks; review of workflow diffs; audit log of
  who approved what.
- Recovery: revert the merge, rotate any credential the job could reach,
  re-run the release from a known-good commit.
- Residual risk: a reviewer approves a subtle backdoor in ordinary code.
  Accepted until: YYYY-MM-DD (review date).  Owner: (role)

### AC-2: Package substitution
### AC-3: Leaked token
### AC-4: Injection through application input
### AC-5: Release artifact replacement

## 3. What are we going to do about it?

Link each abuse case to requirements in docs/security-requirements.md.

## 4. Did we do a good enough job?

- Which abuse cases have a control with automated verification?
- Which rely on a human?  Which have no detection at all?
- When do we revisit this model?  (new feature, new dependency source,
  new deployment target, a real incident, or every 90 days)

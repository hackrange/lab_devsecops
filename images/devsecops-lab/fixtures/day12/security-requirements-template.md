# Security requirements: secure-build-lab

Standard referenced: OWASP ASVS 5.0.0 (record the exact version you used).

## Requirements-to-controls matrix

| ID | Requirement | Control | Verification (evidence) | Owner |
|----|-------------|---------|-------------------------|-------|
| SR-01 | User input cannot become executable code | No eval/new Function in src; input is length-checked data | Semgrep in CI on every PR; unit test "keeps HTML-like input as data" | App team lead |
| SR-02 | Dependencies come from approved sources | | | |
| SR-03 | Pull request code has no release credentials | | | |
| SR-04 | Every release has a traceable component inventory | | | |
| SR-05 | A credential finding triggers a response | | | |

## ASVS requirements selected for this app

| ASVS 5.0.0 ID | Level | What it asks | How we verify it |
|---------------|-------|--------------|------------------|
| | | | |

## Ownership

| Question | Owner |
|----------|-------|
| Who triages a new finding? | |
| Who fixes it? | |
| Who may approve an exception? | |
| Who owns availability when a control (scanner, firewall, gate) is down? | |

## Accepted risks (every one expires)

| Risk | Why accepted | Compensating control | Approved by | Expires |
|------|--------------|----------------------|-------------|---------|
| | | | | |

## Retirement checklist (when this service is shut down)

- [ ] Revoke CI tokens, deploy keys, and cloud roles used by the service
- [ ] Remove secrets from the vault and confirm nothing still reads them
- [ ] Deprecate and delete published images and artifacts (keep evidence copies per policy)
- [ ] Remove DNS records, load balancer routes, and firewall rules
- [ ] Archive the repository (read-only) and remove it from scanners and dashboards
- [ ] Close or transfer open findings and accepted risks
- [ ] Update the asset inventory and the threat model with the retirement date

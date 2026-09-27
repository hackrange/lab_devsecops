#!/bin/bash
# Build ~/fixtures/leaky-repo: a small git history in which a developer commits
# synthetic secrets, then "removes" them in a later commit.  Every value here is
# random or a documented non-functional lab marker; none is a real credential.
# Run once at image build time as the student user.  Author: Tim Rice
set -euo pipefail
R="${1:?target dir}"
rm -rf "$R" && mkdir -p "$R" && cd "$R"
git init -q -b main
git config user.name "Dana Developer"
git config user.email "dana@example.test"
d() { GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1" git commit -q -m "$2"; }

printf '# invoice-service\n\nSends invoices.  Run with node src/index.js\n' > README.md
mkdir -p src config
printf "export const port = 3000;\n" > src/index.js
git add . && d "2026-05-04T09:12:00" "Initial commit"

cat > config/settings.js <<'JS'
// TODO move these somewhere safer before we go live
export const settings = {
  smtpHost: 'smtp.example.test',
  smtpUser: 'invoices',
  smtpPassword: 'LAB_SECRET_SMTPPASSW0RD12AB',
  labToken: 'LAB_SECRET_ABCDEFGHIJKLMNOP',
};
JS
git add . && d "2026-05-06T16:40:00" "Add mail settings"

cat > .env <<'ENV'
DATABASE_URL=postgres://invoices:LAB_SECRET_DBPASSWORD9QZX7K@db.example.test/invoices
PAYMENT_API_KEY=LAB_SECRET_PAYMENTKEY0000001
GITHUB_TOKEN=ghp_Dq1vCNq2oleMhGAm4X6EYqk5KvkErvT4n3mM
ENV
git add . && d "2026-05-07T11:05:00" "Local env for testing"

git rm -q --cached .env && printf '.env\n' > .gitignore && rm -f .env
cat > config/settings.js <<'JS'
export const settings = {
  smtpHost: process.env.SMTP_HOST,
  smtpUser: process.env.SMTP_USER,
  smtpPassword: process.env.SMTP_PASSWORD,
};
JS
git add . && d "2026-05-09T10:30:00" "Remove secrets (oops)"

printf "export function total(items) {\n  return items.reduce((s, i) => s + i.price, 0);\n}\n" > src/total.js
git add . && d "2026-05-12T14:00:00" "Add invoice totals"
echo "built leaky repo at $R with $(git rev-list --count HEAD) commits"

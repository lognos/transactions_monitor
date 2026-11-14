# FINTRAC Policy Update Checker & Ingestion Loop

Monitors FINTRAC Notices/Advisories and Guidance Directives, evaluates effective dates, generates dry-run impact assessments/alerts, and synchronizes active policies into MongoDB Atlas (`memory` collection, `memory_text_idx`).

## 1. Policy Update Checker (`scripts/check_fintrac_policy_updates.py`)

- **Monitored source:** `https://fintrac-canafe.canada.ca/notices-avis/notices-avis-eng`
- **Workflow:** `.github/workflows/fintrac_policy_update_checker.yml` (runs weekly Mondays 08:00 UTC or via `workflow_dispatch` with `dry_run` / `simulate_update`).
- **Effective date urgency classification:**
  - `IN_FORCE_TODAY` / `ALREADY_IN_FORCE` (effective date ≤ today)
  - `URGENT_UPCOMING_30D` (0 < days ≤ 30)
  - `UPCOMING_QUARTER` (30 < days ≤ 90)
  - `FUTURE_TRANSITIONAL` (days > 90)
- **Dry-run mode:** Saves generated HTML/JSON alert previews to `data/fintrac_policy_notifications/` without sending external emails.

```bash
python scripts/check_fintrac_policy_updates.py --dry-run
python scripts/check_fintrac_policy_updates.py --simulate-update
```

## 2. Policy Ingestion Loop (`scripts/policy_ingestion_loop.py`)

Crawls FINTRAC Guidance Directives, FINTRAC Notices/Advisories, and `data/master_canadian_policy_catalog.json` to maintain `data/fintrac_policy_monitoring_catalog.csv` and sync policies into `db.memory` (`kind: "policy"`):

- **Active / Upcoming:** Upserted with `active: True` and searchable text embeddings.
- **Expired (`expiry_date < today` or `status == 'EXPIRED'`):** Soft-deactivated (`active: False`, `expired: True`) so vector search queries filtering `{"active": True}` exclude them; `--purge-expired` physically deletes them from MongoDB while keeping the CSV record.

```bash
python scripts/policy_ingestion_loop.py --dry-run
python scripts/policy_ingestion_loop.py --sync-db
python scripts/policy_ingestion_loop.py --dry-run --simulate-new
python scripts/policy_ingestion_loop.py --sync-db --purge-expired
```

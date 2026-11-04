# BRIGHT SCAFF. Rental Management — Starter

Stack: React + Vite + TypeScript + Tailwind CSS, Python Flask + Flask-Smorest Swagger, MySQL.

## Prerequisites
Node.js 20+, Python 3.11+, MySQL 8+.

## Database
Run `database/schema.sql` in MySQL Workbench.

## Backend (Windows PowerShell)
```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit DATABASE_URL in .env to match your local MySQL user/password
flask --app run run --debug
```
API: http://127.0.0.1:5000 | Swagger: http://127.0.0.1:5000/docs | Health: http://127.0.0.1:5000/api/health

## Frontend (second terminal)
```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```
Frontend: http://localhost:5173

## Current foundation
- Responsive navy/white dashboard using #1C0854 and #03036C
- Dashboard, customer directory, inventory catalogue, and planned-module screens
- Flask health/dashboard endpoints, customer CRUD basics, item CRUD basics
- Swagger/OpenAPI documentation and initial MySQL schema

Dashboard activity/chart rows are demo data until rental transactions are implemented. Do not use for real customer records until authentication, permissions, rental calculations, audit logging, backup/restore and testing are complete.


## Frontend structure (modular)

- `frontend/src/components/layout/` — application sidebar and top bar
- `frontend/src/components/ui/` — reusable modal and placeholder module view
- `frontend/src/pages/` — dashboard, customer directory and inventory screens
- `frontend/src/services/` — API client and formatting helpers
- `frontend/src/types/` — shared TypeScript types
- `frontend/src/data/` — clearly labelled starter/demo data
- `frontend/src/App.tsx` — application state, page routing and modal orchestration only

The global stylesheet uses responsive layout breakpoints and a larger base type scale. Demo dashboard figures and sample activity are illustrative only.

## Audited return corrections (new)
1. Back up the database.
2. In MySQL Workbench, run `database/return_correction_migration.sql` against the existing `bright_scaff` database. This only creates the `rental_return_audit` table if it is missing.
3. Restart Flask and the React frontend.
4. In Rental transactions, choose **Record return**, open the delivery, and use the **Return history** panel. Each active return line has **Edit**, **Delete**, and **Audit** actions.
5. Edit/delete requires a reason. Corrections recalculate the delivery status and rebuild stock movements. Deleted return lines remain recorded in `rental_return_audit`; if all lines are removed, the original return header remains visible as a voided historical entry.

The audit table preserves old return number/date, delivery item, quantity, condition, notes, action, reason and timestamp. The audit is a correction history, not a substitute for a regular database backup. Restrict access to this screen/API to authorized staff before production use.

### Return date and bill submission timestamp
The return history now displays two separate fields:
- **Actual return date**: the business date the items were physically returned (`rental_returns.return_date`); this drives rental calculations.
- **Bill submitted at**: the timestamp when the return bill was entered/created (`rental_returns.created_at`); this is for audit and does not drive rental calculations.

This uses the existing `created_at` column, so no additional migration is needed if the database was created from the included schema/migration.


## Statement export update (31 Oct 2026)

The customer Excel export now follows the simple six-column DATE / BILL NO / PARTICULARS / RENT / RECEIPT / BALANCE layout, with a separate Rental Details sheet for formulas and return events. The PDF is a plain black-and-white statement with no colored boxes or decorative symbols. No database migration is required for this export-only update. The Excel merge_cells TypeError reported in the Flask log is fixed.


## BRIGHT SCAFF ERP foundation update

See `CHANGELOG-ERP-FOUNDATION.md`. Back up the database, then run `database/phase_erp_upgrade.sql` against `bright_scaff` to add optional customer profile, rental metadata and payment storage. Existing records are retained. This migration is additive; review the changelog for financial UI workflows that still require completion before production.

# StudioSuite Business Management System

Responsive business management system for clothing, printing, and photography operations. The workspace now includes an initial React dashboard preview, a Django REST Framework API foundation, and local PostgreSQL configuration. Dashboard figures are sample data only; transaction workflows are not connected yet.

## Local development

1. Copy `.env.example` to `.env` and keep the example credentials for local development only.
2. Start PostgreSQL with `docker compose up -d db`.
3. In `backend/`, create and activate a Python virtual environment, then install `requirements.txt`.
4. From `backend/`, run `python manage.py migrate`, then `python manage.py createsuperuser`.
5. Bootstrap the workspace with `python manage.py setup_organization --name "Kpatawee Studio" --admin-username <your-username>`.
6. Start the API with `python manage.py runserver`.
7. In `frontend/`, run `npm install` and `npm run dev`.

The API health endpoint is `/api/v1/health/`. Session authentication endpoints are under `/api/v1/auth/`; authenticated organization context is available at `/api/v1/organization/` and accepts a membership-validated `X-Organization-ID` header when the user belongs to more than one organization. Provisional policy samples that can be revised are recorded in [discovery decisions](./docs/discovery-decisions.md).

## Documents

- [Product requirements (PRD)](./prd.md) — users, workflows, scope, acceptance criteria, and success measures.
- [02 User flows & UI/UX specification](./user-flows-ui-ux.md) — screen inventory, journey flows, interaction and accessibility guidance.
- [03 System architecture](./system-architecture.md) — application boundaries, deployment view, decisions, and critical sequences.
- [04 Database design (ERD)](./database-design-erd.md) — Mermaid ERD, entity definitions, constraints, and open decisions.
- [05 API specification](./api-specification.md) — REST resources, conventions, examples, and access rules.
- [06 Development task breakdown](./plan.md) — phased implementation tasks and PRD requirement traceability.
- [Technical requirements (TRD)](./trd.md) — implementation constraints, security, reliability, and delivery requirements.
- [Budgetary quotation](./quotation.md) — indicative development and operating costs, assumptions, and exclusions.
- [Requirements checklist](./requirements-checklist.md) — traceability and readiness checks for refinement and delivery.
- [Liberia provider and policy discovery](./provider-research.md) — preliminary provider evidence, pricing snapshot, and open verification/financial decisions.
- [Planning checkpoints](./checkpoints/) — requirement-to-plan and plan-to-task coverage.

## Proposed stack

- Frontend: React with TypeScript; responsive web application installable as a Progressive Web App (PWA).
- Backend: Python with Django and Django REST Framework.
- Database: PostgreSQL.

These are planning documents, not a binding commercial contract. Confirm country, currency, tax rules, and hosting region before MVP implementation; verify provider choices only before starting the deferred integration release.

# CaseMesh

> AICTE Inter-Institutional Case & Grievance Coordination Engine

CaseMesh is an institutional grievance monitoring and case coordination platform designed for AICTE. It features multi-jurisdiction deduplication and overlap detection, cross-agency coordination, SLA tracking, and audit-logged grievance resolution.

---

## Architecture Overview

- **`apps/web`**: Web management portal (React 19, Vite, TanStack Router).
- **`apps/mobile`**: Mobile application (React Native / Expo).
- **`backend`**: FastAPI backend service with PostgreSQL, SQLAlchemy, Alembic, and Valkey/Redis integration.
- **`rules`**: Standalone deterministic overlap detection and business days calculation engine.
- **`packages/ui-tokens`**: Shared design tokens (colors, typography, elevation, icons) with WCAG 2.2 AA contrast compliance.
- **`packages/ui-web`**: Reusable component system for web clients.
- **`packages/api-client`**: Generated TypeScript API client for the backend OpenAPI specification.
- **`packages/i18n`**: Multi-language translation catalog (English, Hindi, Tamil).

---

## Quick Start

### Prerequisites

- Node.js >= 22 & pnpm >= 11
- Python >= 3.12
- Docker & Docker Compose (for local PostgreSQL and Valkey services)

### Setup & Development

1. **Install JavaScript dependencies:**
   ```bash
   pnpm install
   ```

2. **Set up Python environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e rules
   pip install -e "backend[dev]"
   ```

3. **Start infrastructure services:**
   ```bash
   docker compose -f infra/docker-compose.yml up -d
   ```

4. **Run migrations:**
   ```bash
   cd backend
   alembic upgrade head
   ```

5. **Start frontend and backend:**
   ```bash
   # From the workspace root
   pnpm dev
   ```

---

## Testing & Quality Gates

- **Typecheck & Build:**
  ```bash
  pnpm turbo run build
  pnpm turbo run typecheck
  ```
- **Rules Tests:**
  ```bash
  cd rules && pytest -q
  ```
- **Design Contrast Guard:**
  ```bash
  pnpm guard:contrast
  ```
- **Guards:**
  ```bash
  pnpm guard:all
  # Or run individually:
  # pnpm guard:data-origin
  # pnpm guard:icons
  # pnpm guard:contrast
  ```

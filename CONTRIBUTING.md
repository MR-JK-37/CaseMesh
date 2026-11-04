# Contributing Guidelines

Thank you for contributing to CaseMesh! We welcome issues, suggestions, and pull requests to make grievance coordination more reliable, secure, and accessible.

## Code of Conduct

Please be respectful and constructive in all communication with community members and maintainers.

## Development Workflow

1. Fork and clone the repository.
2. Create a topic branch: `git checkout -b feature/your-feature-name`.
3. Install dependencies:
   ```bash
   pnpm install
   pip install -e rules
   pip install -e "backend[dev]"
   ```
4. Run validation checks before committing:
   ```bash
   pnpm guard:all
   pnpm turbo run typecheck
   cd rules && pytest -q
   ```
5. Submit a pull request with a descriptive title and summary of changes.


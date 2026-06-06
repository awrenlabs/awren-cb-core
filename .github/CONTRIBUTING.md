# Contributing to Awren Core

## Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Install dependencies: `make install`
4. Make your changes
5. Run tests: `make test`
6. Submit a pull request

## Development Setup

See [docs/onboarding/developer-guide.md](docs/onboarding/developer-guide.md) for detailed setup instructions.

## Pull Request Process

1. Ensure all tests pass
2. Update documentation if needed
3. Add or update ADRs for architecture changes
4. Request review from at least one maintainer

## Code Standards

- Follow [PEP 8](https://peps.python.org/pep-0008/) for Python code
- Use type hints for all public interfaces
- Write docstrings for all public functions and classes
- Ensure >80% test coverage for new code
- Follow the [Engineering Standards](docs/standards/coding-standards.md)

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add ontology versioning support
fix: resolve SHACL validation edge case
docs: update memory architecture documentation
```

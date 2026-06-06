# Testing Standards

## Test Levels
- **Unit Tests**: Individual functions and classes
- **Integration Tests**: Service interactions with databases
- **E2E Tests**: Full system workflows
- **Benchmark Tests**: Performance regression detection

## Requirements
- All new code must have tests
- Tests must be deterministic
- Mock external services in unit tests
- Use pytest markers: @pytest.mark.unit, @pytest.mark.integration, @pytest.mark.e2e, @pytest.mark.slow

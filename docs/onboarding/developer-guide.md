# Developer Onboarding Guide

## Prerequisites
- Python 3.12+
- Poetry
- Docker & Docker Compose
- Git

## Setup
```bash
git clone https://github.com/awren-labs/awren-core.git
cd awren-core
make install
make infra-up
make migrate
make api-dev
```

## Project Structure
See README.md for full structure.

## First Tasks
1. Read the ADRs in docs/adr/
2. Explore the packages in packages/
3. Run the tests: make test
4. Start the API: make api-dev

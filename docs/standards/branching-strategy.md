# Branching Strategy

## Main Branches
- **main**: Production, always deployable
- **develop**: Latest delivered changes

## Supporting Branches
- **feature/<name>**: New features (branch from develop, merge to develop)
- **fix/<name>**: Bug fixes (branch from develop, merge to develop)
- **release/<version>**: Release prep (branch from develop, merge to main + develop)
- **hotfix/<name>**: Urgent fixes (branch from main, merge to main + develop)

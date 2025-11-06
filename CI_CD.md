# CI/CD Pipeline Documentation

## Overview

This repository uses GitHub Actions for continuous integration and continuous deployment (CI/CD). The pipeline automatically tests, builds, and validates code on every push and pull request.

## Workflows

### 1. CI Pipeline (`ci.yml`)

**Triggers:** Push to `master`/`main`/`develop` branches, Pull Requests

**Jobs:**

#### Test Job

- **Runs on:** Ubuntu Latest
- **Python Versions:** 3.11, 3.12
- **Steps:**
  - Checkout code
  - Setup Python with caching
  - Install Poetry and dependencies
  - Run pytest with coverage (minimum 80%)
  - Upload coverage to Codecov
  - Generate coverage reports

#### Lint Job

- **Runs on:** Ubuntu Latest
- **Steps:**
  - Code formatting check with Black
  - Linting with Ruff
  - Type checking with mypy

#### Docker Job

- **Runs on:** Ubuntu Latest
- **Steps:**
  - Build Docker image (multi-stage)
  - Test Docker image functionality
  - Validate docker-compose configuration
  - Uses buildx for caching

#### Security Job

- **Runs on:** Ubuntu Latest
- **Steps:**
  - Scan dependencies with Safety
  - Security linting with Bandit
  - Vulnerability detection

### 2. Docker Publish (`docker-publish.yml`)

**Triggers:** Push to `master`/`main`, Tags `v*.*.*`, Releases

**Features:**

- Builds and pushes to GitHub Container Registry (ghcr.io)
- Multi-platform support (amd64, arm64)
- Automatic tagging:
  - `latest` for main branch
  - `v1.2.3` for version tags
  - `sha-<commit>` for commits
- Build provenance attestation

**Environment Variables:**

- `REGISTRY`: ghcr.io
- `IMAGE_NAME`: ${{ github.repository }}

### 3. CodeQL Analysis (`codeql.yml`)

**Triggers:** Push, Pull Requests, Weekly schedule (Mondays)

**Features:**

- Security and quality analysis
- Python code scanning
- Automated vulnerability detection
- Weekly security audits

### 4. Dependency Review (`dependency-review.yml`)

**Triggers:** Pull Requests only

**Features:**

- Reviews dependency changes in PRs
- Fails on moderate+ severity vulnerabilities
- Blocks GPL-2.0 and GPL-3.0 licenses

### 5. Dependabot (`dependabot.yml`)

**Schedule:** Weekly on Mondays at 09:00

**Monitors:**

- Python dependencies (pip)
- GitHub Actions versions
- Docker base images

**Configuration:**

- Max 10 PRs for Python deps
- Max 5 PRs for Actions/Docker
- Auto-assigns to @Achu-Anil
- Labels: `dependencies`, `python`, `github-actions`, `docker`

## Status Badges

Add these to your README.md:

```markdown
[![CI Pipeline](https://github.com/Achu-Anil/aiq-depth-frames-api/actions/workflows/ci.yml/badge.svg)](https://github.com/Achu-Anil/aiq-depth-frames-api/actions/workflows/ci.yml)
[![Docker Publish](https://github.com/Achu-Anil/aiq-depth-frames-api/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Achu-Anil/aiq-depth-frames-api/actions/workflows/docker-publish.yml)
[![CodeQL](https://github.com/Achu-Anil/aiq-depth-frames-api/actions/workflows/codeql.yml/badge.svg)](https://github.com/Achu-Anil/aiq-depth-frames-api/actions/workflows/codeql.yml)
```

## Local Testing

Before pushing, test locally to avoid CI failures:

```bash
# Run tests
poetry run pytest --cov=app --cov-report=term-missing

# Check formatting
poetry run black --check app/ tests/

# Lint code
poetry run ruff check app/ tests/

# Type check
poetry run mypy app/

# Build Docker
docker build -t aiq-depth-frames-api:local .

# Validate docker-compose
docker-compose config
```

## Coverage Requirements

- **Minimum Coverage:** 80%
- **Measured by:** pytest-cov
- **Uploaded to:** Codecov (optional)
- **Fails if:** Coverage drops below threshold

## Security Scanning

### Tools Used:

1. **Safety** - Python dependency vulnerability scanner
2. **Bandit** - Python security linter
3. **CodeQL** - GitHub's semantic code analysis
4. **Dependabot** - Automated dependency updates

### Security Policies:

- Moderate+ severity vulnerabilities fail PRs
- GPL licenses are blocked
- Weekly automated scans

## Docker Registry

Images are published to GitHub Container Registry:

```bash
# Pull latest
docker pull ghcr.io/achu-anil/aiq-depth-frames-api:latest

# Pull specific version
docker pull ghcr.io/achu-anil/aiq-depth-frames-api:v1.0.0

# Pull by commit SHA
docker pull ghcr.io/achu-anil/aiq-depth-frames-api:master-abc1234
```

## Workflow Permissions

Required GitHub permissions:

- `contents: read` - Read repository
- `packages: write` - Push to GHCR
- `security-events: write` - CodeQL alerts
- `actions: read` - Workflow access

## Caching Strategy

All workflows use GitHub Actions cache:

- **Poetry dependencies** - Cached by poetry.lock hash
- **Docker layers** - Cached with GitHub Actions cache
- **pip packages** - Cached by requirements hash

## Debugging Failed Workflows

1. **Check workflow logs:**

   - Go to Actions tab
   - Click on failed workflow
   - Expand failed step

2. **Common issues:**

   - Poetry lock file out of sync: `poetry lock --no-update`
   - Test failures: `poetry run pytest -v`
   - Linting errors: `poetry run black app/ tests/`
   - Type errors: `poetry run mypy app/`

3. **Re-run failed jobs:**
   - Click "Re-run failed jobs" in Actions UI

## Release Process

### Creating a Release:

1. **Update version:**

   ```bash
   poetry version patch  # or minor, major
   git add pyproject.toml
   git commit -m "chore: bump version to $(poetry version -s)"
   ```

2. **Create tag:**

   ```bash
   git tag -a v$(poetry version -s) -m "Release v$(poetry version -s)"
   git push origin v$(poetry version -s)
   ```

3. **Create GitHub Release:**

   - Go to Releases → Draft a new release
   - Select the tag
   - Generate release notes
   - Publish release

4. **Docker image automatically built and pushed**

## Environment Variables

### Required Secrets:

- `GITHUB_TOKEN` - Automatically provided

### Optional Secrets:

- `CODECOV_TOKEN` - For Codecov integration
- `SLACK_WEBHOOK` - For notifications (not configured)

## Monitoring

View CI/CD metrics:

- **Actions tab** - All workflow runs
- **Insights → Community** - Standards badges
- **Security → Dependabot** - Dependency alerts
- **Security → Code scanning** - CodeQL alerts

## Contributing

When submitting PRs:

1. Ensure all tests pass locally
2. Run linting and formatting
3. Wait for CI to complete
4. Address any CI failures before review

## Future Enhancements

Potential additions:

- [ ] Deployment to staging/production
- [ ] Performance benchmarking
- [ ] Integration tests with databases
- [ ] API documentation generation
- [ ] Slack/Discord notifications
- [ ] Release automation
- [ ] Helm charts for Kubernetes

## Support

For CI/CD issues:

1. Check workflow logs
2. Review this documentation
3. Open an issue with `ci` label
4. Contact repository maintainer

---

**Last Updated:** November 6, 2025  
**Maintained by:** @Achu-Anil

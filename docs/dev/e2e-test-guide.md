# E2E Integration Test Guide

End-to-end tests that exercise the full AutoBangumi workflow against real
Docker services (qBittorrent + mock RSS server).

## Prerequisites

- **Docker** with `docker compose` (v2)
- **uv** for Python dependency management
- Ports **7892**, **18080**, **18888** must be free

## Quick Start

```bash
# 1. Build the mock RSS server image
cd backend/src/test/e2e
docker build -f Dockerfile.mock-rss -t ab-mock-rss .

# 2. Start test infrastructure
docker compose -f docker-compose.test.yml up -d --wait

# 3. Verify services are healthy
docker compose -f docker-compose.test.yml ps

# 4. Run E2E tests
cd backend && uv run pytest -m e2e -v --tb=long

# 5. Cleanup
docker compose -f backend/src/test/e2e/docker-compose.test.yml down -v
```

## Architecture

```
Host machine
├── pytest (test runner)
│   └── Drives HTTP requests to AutoBangumi at localhost:7892
├── AutoBangumi subprocess
│   ├── Isolated config/ and data/ in temp directory
│   └── Uses mock downloader (no real qB coupling during setup)
├── qBittorrent container (localhost:18080)
│   └── linuxserver/qbittorrent:latest
└── Mock RSS server container (localhost:18888)
    └── Serves static XML fixtures from fixtures/
```

## Test Phases

| Phase | Tests | What It Validates |
|-------|-------|-------------------|
| 1. Setup Wizard | `test_01` - `test_06` | First-run detection, mock downloader, setup completion, 403 guard |
| 2. Authentication | `test_10` - `test_13` | Login, cookie-based JWT, token refresh, logout |
| 3. Configuration | `test_20` - `test_22` | Config CRUD, password masking |
| 4. RSS Management | `test_30` - `test_32` | Add, list, delete RSS feeds |
| 5. Program Lifecycle | `test_40` - `test_41` | Status check, restart |
| 6. Downloader | `test_50` - `test_51` | Mock downloader health, direct qB connectivity |
| 7. Cleanup | `test_90` | Logout |

## Key Design Decisions

### Mock Downloader for Setup

The setup wizard's `_validate_url()` blocks private/loopback IPs (SSRF
protection). Since the Docker qBittorrent instance is on `localhost`, the
setup wizard's "test downloader" endpoint would reject it. Instead:

1. Setup uses `downloader_type: "mock"` (bypasses URL validation)
2. Config can be updated to point to real qBittorrent after auth
3. Direct qBittorrent connectivity is tested independently (`test_51`)

### DEV_VERSION Auth Bypass

When running from source, `VERSION == "DEV_VERSION"` which bypasses JWT
validation (`get_current_user` returns `"dev_user"` unconditionally). Tests
document this behavior: login/refresh/logout endpoints still work, but
unauthenticated access is also allowed. In production builds, test_13
would expect HTTP 401.

### CWD-Based Isolation

AutoBangumi resolves all paths relative to the working directory:
- `config/` - config files, JWT secret, setup sentinel
- `data/` - SQLite database, posters, logs

The `ab_process` fixture creates a temp directory with these subdirs and
runs `main.py` from there, ensuring complete isolation from any existing
installation.

### qBittorrent Password Extraction

Recent `linuxserver/qbittorrent` images generate a random temporary
password on first start. The `qb_password` fixture polls `docker logs`
until it finds the line:

```
A temporary password is provided for this session: XXXXXXXX
```

## Debugging Failures

### AutoBangumi won't start

```bash
# Check if port 7892 is in use
lsof -i :7892

# Run manually to see startup logs
cd /tmp/test-workdir && uv run python /path/to/backend/src/main.py
```

### qBittorrent issues

```bash
docker logs ab-test-qbittorrent
docker exec ab-test-qbittorrent curl -s http://localhost:18080
```

### Mock RSS server issues

```bash
docker logs ab-test-mock-rss
curl http://localhost:18888/health
curl http://localhost:18888/rss/mikan.xml
```

### Test infrastructure stuck

```bash
# Force cleanup
docker compose -f backend/src/test/e2e/docker-compose.test.yml down -v --remove-orphans
```

## Adding New Test Scenarios

1. Add new test methods to `TestE2EWorkflow` in definition order
2. Use `api_client` for HTTP requests (cookies persist across tests)
3. Use `e2e_state` dict to share data between tests
4. For new RSS fixtures, add XML files to `fixtures/` directory
5. Keep test names ordered: `test_XX_description` where XX reflects the phase

### Adding a new fixture feed

1. Create `backend/src/test/e2e/fixtures/your_feed.xml`
2. Access via `http://localhost:18888/rss/your_feed.xml`
3. Rebuild the mock RSS image: `docker compose ... build mock-rss`

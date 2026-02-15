# External Integrations

**Analysis Date:** 2026-02-16

## APIs & External Services

**Government APIs:**
- ECT (Election Commission of Thailand) API
  - Purpose: Official election reference data validation
  - Endpoints:
    - `https://static-ectreport69.ect.go.th/data/data/refs/info_province.json` - Province data
    - `https://static-ectreport69.ect.go.th/data/data/refs/info_constituency.json` - Constituency data
    - `https://static-ectreport69.ect.go.th/data/data/refs/info_party_overview.json` - Party overview
    - `https://static-ectreport69.ect.go.th/data/data/refs/info_mp_candidate.json` - MP candidates
    - `https://static-ectreport69.ect.go.th/data/data/refs/info_party_candidate.json` - Party candidates
    - `https://stats-ectreport69.ect.go.th/data/records/stats_cons.json` - Constituency statistics
    - `https://stats-ectreport69.ect.go.th/data/records/stats_party.json` - Party statistics
  - SDK/Client: Custom Python client (`ect_api.py`)
  - Auth: None required (public endpoints)
  - Cache: LRU caching implemented in `ect_api.py` line 45

**Google Services:**
- Google Drive API
  - Purpose: Ballot image storage and retrieval
  - SDK/Client: `google-api-python-client` v2.190.0
  - Auth: OAuth 2.0 (`drive_auth.py` lines 10-12)
    - Scopes: `['https://www.googleapis.com/auth/drive.readonly']`
    - Credentials: `~/.claude/.google/client_secret.json`
  - Alternative: `gdown` v5.2.1 for direct file downloads
  - Endpoints:
    - `https://drive.google.com/open?id={id}` - File URLs
    - `https://drive.usercontent.google.com/download?id={id}&export=download&authuser=0` - Downloads
    - `https://drive.google.com/embeddedfolderview?id={id}` - Folder views

## Data Storage

**Databases:**
- Local JSON files - Election reference data caching
  - `data/provinces.json`, `data/constituencies.json`, etc.
- File storage: Google Drive as primary ballot image repository

**File Storage:**
- Google Drive - Primary storage for ballot images
- Local filesystem - Temporary processing and result storage

**Caching:**
- LRU cache in `ect_api.py` for government API responses
- Token caching for Google Drive authentication

## Authentication & Identity

**Auth Provider:**
- Google OAuth 2.0
  - Implementation: `google-auth-oauthlib` and `google-auth-httplib2`
  - Flow: Installed app flow with token persistence
  - Token location: `~/.claude/.google/token.pickle`

## Monitoring & Observability

**Error Tracking:**
- Custom error handling in each module
- Basic print statements for progress tracking
- No external monitoring service integration

**Logs:**
- Python logging (minimal)
- Console output for processing results
- JSON output for structured results (`test_result_*.json`)

## CI/CD & Deployment

**Hosting:**
- No deployment platform specified
- Local script execution
- Git repository for version control

**CI Pipeline:**
- None detected
- Manual execution workflow

## Environment Configuration

**Required env vars:**
- No environment variables directly referenced
- Implicit: Credentials must be present at `~/.claude/.google/client_secret.json`

**Secrets location:**
- Google OAuth credentials: `~/.claude/.google/client_secret.json`
- OAuth token cache: `~/.claude/.google/token.pickle`
- Note: Secrets are stored outside repository but in user's .claude directory

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

---

*Integration audit: 2026-02-16*
```
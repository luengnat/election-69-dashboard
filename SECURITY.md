# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.1.x   | :white_check_mark: |
| 1.0.x   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please report it responsibly.

### How to Report

**DO NOT** open a public issue for security vulnerabilities.

Instead, please:

1. Email security details to the maintainers (or create a private security advisory on GitHub)
2. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 7 days
- **Status Updates**: Every 7 days until resolved
- **Disclosure**: After fix is released

## Security Best Practices

When using this application:

### API Keys

- **Never commit API keys** to version control
- Use environment variables (`.env` file, not committed)
- Rotate keys if they may have been exposed

```bash
# Set environment variables
export OPENROUTER_API_KEY="your-key-here"
export ANTHROPIC_API_KEY="your-key-here"
```

### Web UI Security

- Default binding is `127.0.0.1` (localhost only)
- To expose externally, set `WEB_UI_HOST=0.0.0.0` (not recommended without authentication)
- Consider using a reverse proxy with HTTPS for production

### File Uploads

- Maximum file size: 10MB per file
- Maximum batch size: 500 files
- Allowed file types: `.png`, `.jpg`, `.jpeg`, `.pdf`

### Docker Deployment

```bash
# Build and run with environment variables
docker-compose up -d

# Or with explicit secrets
docker run -e OPENROUTER_API_KEY="..." -p 7860:7860 election-ocr
```

## Known Security Considerations

1. **No Authentication**: The web UI does not include built-in authentication. Deploy behind a reverse proxy with auth if needed.

2. **External API Calls**: OCR processing sends image data to external APIs (OpenRouter, Anthropic). Ensure this complies with your data handling requirements.

3. **Input Validation**: File uploads are validated for type and size, but additional sanitization may be needed for specific deployments.

## Security Features

- Input validation for all file uploads
- Path sanitization for generated files
- API request timeouts to prevent hanging
- Rate limiting for API calls
- Non-root Docker user
- No hardcoded credentials

## Security Checklist

Before deploying:

- [ ] API keys stored in environment variables
- [ ] `.env` file not committed to version control
- [ ] Web UI bound to appropriate host (127.0.0.1 or behind auth)
- [ ] HTTPS enabled if exposed externally
- [ ] Rate limits configured appropriately
- [ ] Log output monitored for security events

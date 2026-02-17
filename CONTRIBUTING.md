# Contributing to Thai Election Ballot OCR

Thank you for your interest in contributing! This document provides guidelines for contributions.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/election.git`
3. Install dependencies: `make install` or `pip install -r requirements.txt`
4. Set up pre-commit hooks: `pip install pre-commit && pre-commit install`

## Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
make install

# Install development tools
make dev
```

## Running Tests

```bash
# Run all tests
make test

# Run accuracy tests (requires API keys)
make test-accuracy
```

## Code Style

This project uses:
- **ruff** for linting and formatting
- **Type hints** where practical
- **Docstrings** for public functions

Run linting:
```bash
make lint
```

Format code:
```bash
make format
```

## Commit Messages

Follow conventional commits format:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Adding/updating tests
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks

Example:
```
feat: add support for ส.ส. 5/19 form type

- Add form type enum value
- Update OCR prompts
- Add tests for new form type
```

## Pull Request Process

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make your changes
3. Run tests: `make test`
4. Run linting: `make lint`
5. Commit your changes
6. Push to your fork
7. Create a pull request

### PR Requirements

- All tests must pass
- Code must be formatted with ruff
- New features require tests
- Breaking changes require documentation updates

## Security

- **Never commit API keys** - Use environment variables
- **Report security issues privately** - Do not open public issues for security vulnerabilities
- **Sanitize logs** - Remove sensitive data before sharing

## Project Structure

```
.
├── ballot_ocr.py        # Core OCR extraction
├── batch_processor.py   # Parallel processing
├── web_ui.py            # Gradio web interface
├── ect_api.py           # ECT data integration
├── metadata_parser.py   # Path-based metadata
├── tests/               # Test suite
└── .github/             # CI/CD and templates
```

## Questions?

Open an issue with the `question` label or start a discussion.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

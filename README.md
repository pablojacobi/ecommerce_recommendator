# Ecommerce Recommendator

[![CI](https://github.com/pablojacobi/ecommerce_recommendator/actions/workflows/ci.yml/badge.svg)](https://github.com/pablojacobi/ecommerce_recommendator/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Django 5.1](https://img.shields.io/badge/django-5.1-green.svg)](https://www.djangoproject.com/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

AI-powered product recommendation system that searches across MercadoLibre and eBay marketplaces using natural language queries.

## Features

- **Natural Language Search**: Ask for products in plain language (e.g., "Find me a budget gaming laptop that can run Fortnite at FHD")
- **Multi-Marketplace**: Search across eBay (US) and MercadoLibre (18+ Latin American countries)
- **Price Comparison**: Compare prices across different marketplaces
- **Import Cost Calculator**: Estimate total costs including shipping and import taxes
- **Conversational Refinement**: Refine results through conversation ("Show me the cheapest one", "Filter by good seller reputation")
- **AI-Powered**: Uses Google Gemini for query understanding and recommendations

## Tech Stack

- **Backend**: Django 5.1 + Django REST Framework
- **AI**: Google Gemini 2.0
- **Database**: PostgreSQL (Supabase)
- **Cache**: Redis
- **Frontend**: Django Templates + Tailwind CSS + HTMX
- **Testing**: pytest (100% coverage)
- **CI/CD**: GitHub Actions + Railway

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Redis 7+

### Installation

1. Clone the repository:
```bash
git clone https://github.com/pablojacobi/ecommerce_recommendator.git
cd ecommerce_recommendator
```

2. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements/development.txt
```

4. Copy environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Run migrations:
```bash
python manage.py migrate
```

6. Start the development server:
```bash
python manage.py runserver
```

### Running Tests

```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_health.py

# Run with verbose output
pytest -v
```

### Code Quality

```bash
# Run linter
ruff check .

# Run formatter
ruff format .

# Run type checker
mypy .

# Run all pre-commit hooks
pre-commit run --all-files
```

## Project Structure

```
ecommerce_recommendator/
├── apps/
│   ├── accounts/       # User authentication
│   ├── chat/           # Chat interface
│   └── search/         # Search functionality
├── core/               # Django settings and configuration
├── services/           # External service integrations
├── templates/          # HTML templates
├── tests/              # Test suite
└── requirements/       # Dependencies
```

## API Documentation

Once running, API documentation is available at:
- Swagger UI: http://localhost:8000/api/docs/
- OpenAPI Schema: http://localhost:8000/api/schema/

## Contributing

1. Create a feature branch: `git checkout -b feat/your-feature`
2. Make your changes following conventional commits
3. Run tests and linting: `pytest && ruff check . && mypy .`
4. Create a Pull Request

### Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `test:` Tests
- `chore:` Maintenance
- `ci:` CI/CD changes
- `refactor:` Code refactoring

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

**Pablo Jacobi** - [GitHub](https://github.com/pablojacobi)

# DevLog

A developer time-tracking API built with FastAPI and SQLite.

Track your work hours across projects, generate weekly summaries, and export reports in Markdown or CSV format.

## Installation

```bash
pip install -e .
```

## Usage

### Start the API server

```bash
uvicorn devlog.app:app --reload --port 8000
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/v1/entries | List all time entries |
| POST | /api/v1/entries | Create a time entry |
| GET | /api/v1/entries/{id} | Get a specific entry |
| PUT | /api/v1/entries/{id} | Update an entry |
| DELETE | /api/v1/entries/{id} | Delete an entry |
| GET | /api/v1/projects | List all projects |
| POST | /api/v1/projects | Create a project |
| GET | /api/v1/reports/weekly | Get weekly summary |

### CLI (Coming Soon)

```bash
# Initialize configuration
devlog config init

# Log time from the terminal
devlog log 2h "Implemented auth middleware" --project api-backend

# View weekly summary
devlog summary --week
```

See `devlog/cli.py` for available commands.

## Development

```bash
# Run tests
pytest

# Run linting
ruff check devlog/

# Type checking
mypy devlog/
```

## Architecture

See `docs/ARCHITECTURE.md` for a detailed overview of the system design.

## License

MIT

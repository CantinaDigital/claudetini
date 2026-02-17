# DevLog Roadmap

## Milestone 1 - Core Data Layer (100% complete)
- [x] Create SQLite database schema
- [x] Implement TimeEntry model
- [x] Implement Project model
- [x] Add CRUD operations for time entries
- [x] Add CRUD operations for projects
- [x] Write migration script

## Milestone 2 - API Layer (75% complete)
- [x] Set up FastAPI app structure
- [x] Create time entry endpoints (CRUD)
- [x] Create project endpoints (CRUD)
- [ ] Add pagination to list endpoints
- [x] Add input validation with Pydantic
- [x] Add error handling middleware
- [ ] Add rate limiting
- [x] Write API integration tests

## Milestone 3 - Reporting & Export (25% complete)
- [x] Weekly summary aggregation
- [ ] Monthly summary aggregation
- [ ] Markdown export for weekly reports
- [ ] CSV export for time entries
- [x] Tag-based filtering
- [ ] Date range queries with timezone support
- [ ] Project-level time totals

## Milestone 4 - Polish & Deploy (0% complete)
- [ ] Add CLI interface with Click
- [ ] Configuration file support (.devlog.toml)
- [ ] Docker Compose setup
- [ ] API documentation with OpenAPI
- [ ] Performance benchmarks
- [ ] User guide in docs/

"""
Magneetar Domain Layer

Domain modules encapsulate business logic for a single bounded context.
Each domain owns its data access, validation rules, and domain events.

Domains do NOT:
- Import from other domains directly (communicate via events)
- Import FastAPI objects (framework-agnostic by design)
- Own database connection setup (handled by infrastructure layer)

Event Bus Contract:
- Each domain publishes domain events (e.g. `theft_detected`, `command_sent`)
- Events are plain dicts with a required `event_type` key
- The notification domain subscribes to all cross-domain events
- Events are async-first; the Redis Streams bus is the transport
"""

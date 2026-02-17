"""Example configuration for DevLog.

Copy this file to config.py and update the values for your environment.
"""

# Database configuration
DATABASE_URL = "postgres://user:password@localhost/devlog"
DATABASE_POOL_SIZE = 5

# Server configuration
HOST = "0.0.0.0"
PORT = 8000
DEBUG = True

# Optional: Sentry error tracking
SENTRY_DSN = ""

# Optional: Log level
LOG_LEVEL = "INFO"

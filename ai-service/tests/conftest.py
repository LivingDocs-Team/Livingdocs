"""Test-wide settings, loaded before any test module imports the app."""
import os

# Keep custom templates in memory during tests (never write data/templates.json).
os.environ["TEMPLATES_FILE"] = ""
# Same for versioned documents (never write data/documents.json).
os.environ["DOCUMENTS_FILE"] = ""




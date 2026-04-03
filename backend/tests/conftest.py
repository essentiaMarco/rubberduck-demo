"""Test configuration and shared fixtures."""

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Override settings before importing app modules
os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["SQLITE_PATH"] = os.path.join(os.environ["DATA_DIR"], "test.db")
os.environ["DUCKDB_PATH"] = os.path.join(os.environ["DATA_DIR"], "test.duckdb")

from rubberduck.db.models import Base


@pytest.fixture
def db_session():
    """Create a fresh in-memory database for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_text_file(tmp_dir):
    """Create a sample text file for testing."""
    path = tmp_dir / "sample.txt"
    path.write_text("Hello, this is a test document.\nIt has multiple lines.\nJohn Smith called jane@example.com.")
    return path


@pytest.fixture
def sample_csv_file(tmp_dir):
    """Create a sample CSV file for testing."""
    path = tmp_dir / "data.csv"
    path.write_text("name,email,phone\nJohn Smith,john@example.com,555-123-4567\nJane Doe,jane@example.com,555-987-6543")
    return path

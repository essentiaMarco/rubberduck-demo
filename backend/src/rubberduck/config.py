"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All settings for Rubberduck. Loaded from .env or environment."""

    # ── Data directories ───────────────────────────────────
    data_dir: Path = Path("./data")
    originals_dir: Path = Path("./data/originals")
    parsed_dir: Path = Path("./data/parsed")
    exports_dir: Path = Path("./data/exports")
    osint_dir: Path = Path("./data/osint_captures")
    parquet_dir: Path = Path("./data/parquet")

    # ── Database ───────────────────────────────────────────
    sqlite_path: Path = Path("./data/rubberduck.db")
    duckdb_path: Path = Path("./data/rubberduck.duckdb")

    # ── Server ─────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_port: int = 3000

    # ── Logging ────────────────────────────────────────────
    log_level: str = "INFO"
    log_file: Path = Path("./data/rubberduck.log")

    # ── NLP ────────────────────────────────────────────────
    spacy_model: str = "en_core_web_sm"

    # ── OCR ────────────────────────────────────────────────
    tesseract_cmd: str = "tesseract"
    ocr_enabled: bool = True

    # ── Timezone ───────────────────────────────────────────
    default_timezone: str = "America/Los_Angeles"

    # ── Court ──────────────────────────────────────────────
    default_court: str = "San Francisco Superior Court, Probate Division"

    # ── Jobs ───────────────────────────────────────────────
    max_workers: int = 4

    # ── Ingestion ──────────────────────────────────────────
    max_archive_depth: int = 5
    hash_chunk_size: int = 65536  # 64KB

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def ensure_directories(self) -> None:
        """Create all data directories if they don't exist."""
        for d in [
            self.data_dir,
            self.originals_dir,
            self.parsed_dir,
            self.exports_dir,
            self.osint_dir,
            self.parquet_dir,
            self.parquet_dir / "events",
            self.parquet_dir / "communications",
        ]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()

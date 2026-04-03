# Rubberduck Backend

Local-first digital forensic investigative platform.

## Setup

```bash
pip install -e ".[dev]"
python -m spacy download en_core_web_sm
```

## Run

```bash
uvicorn src.rubberduck.main:app --reload --port 8000
```

## Test

```bash
pytest tests/ -v
```

# Windows collector

This folder now contains a real **Windows foreground-window tracker**.

What it does:
- reads the current foreground window title
- reads the owning process name
- classifies the activity as productive / neutral / distracting
- detects idle time from last keyboard or mouse input
- posts activity slices to the FastAPI backend you already have running

## Files

- `collector_windows.py` - real Windows tracker
- `productivity_rules.example.json` - copy this to `productivity_rules.json` and edit it for your workflow
- `requirements.txt` - Python dependencies for the agent
- `collector_stub.py` - old fake demo sender, keep only for testing

## Install

```bash
cd agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy productivity_rules.example.json productivity_rules.json
```

## Run

Make sure your FastAPI backend is already running on `http://127.0.0.1:8000`.

```bash
python collector_windows.py
```

## Useful environment variables

```bash
set TRACKER_API_BASE_URL=http://127.0.0.1:8000
set TRACKER_POLL_SECONDS=2
set TRACKER_MAX_SEGMENT_SECONDS=20
set TRACKER_IDLE_THRESHOLD_SECONDS=300
set TRACKER_RULES_PATH=C:\path\to\productivity_rules.json
```

## Notes

- Browser URLs are not captured yet. Right now the collector stores the browser **window title/tab title** only.
- The first useful improvement after this is to add browser-extension support for exact domain/URL capture.
- Classification is intentionally rule-based so you can tune it without changing backend code.

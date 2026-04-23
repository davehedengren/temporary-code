# Regalia ID

Upload a photo of academic regalia (graduation robes, hoods, tams) and get back the most likely university, degree level, and field of study.

Uses Claude Opus 4.7 vision to analyze hood linings, velvet trim, and insignia.

## Run on Replit

1. Import this directory as a Repl
2. Add `ANTHROPIC_API_KEY` in Secrets
3. Click Run

## Run locally

```bash
cd regalia-id
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python3 main.py
```

Open http://localhost:5000

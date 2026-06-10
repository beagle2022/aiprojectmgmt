# AI PM Copilot

Agentic AI Project Management Copilot for software development teams.

## Quick start

```bash
# 1. Clone / download the project
cd ai_pm_copilot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 4. Run
python main.py
```

## Alternative: install as a package

```bash
pip install -e .       # installs in editable mode
pm-copilot             # run via the console script
# or
python -m copilot      # run as a module
```

## Run tests

```bash
# From the project root:
python -m pytest tests/ -v

# From any directory:
python -m pytest ai_pm_copilot/tests/ -v
```

## Troubleshooting

**`ModuleNotFoundError: No module named 'copilot'`**  
Run from the project root directory, or install with `pip install -e .`

**`ANTHROPIC_API_KEY not set`**  
Copy `.env.example` to `.env` and add your key.

**Jira / GitHub / Slack not configured**  
The copilot runs in demo mode without these — all tool calls return realistic stub data.

# Brompt Engine

High-performance, zero-trust AI middleware runtime for deterministic LLM execution.

## Features

- **Zero-Trust Guardrail Pipeline** -- Sanitizes both ingress and egress payloads against adversarial prompt injection patterns.
- **Virtual State Paging** -- O(1) state architecture that prevents unbounded context token growth.
- **Strict Structural Enforcement** -- Pydantic v2 validation cores for guaranteed output schemas.

## Quick Start

```bash
# Clone
git clone https://github.com/Azzouzoumnia/Brompt.git
cd Brompt

# Install
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Launch CLI
brompt
```

## Project Structure

```
brompt-engine/
├── src/brompt/
│   ├── __init__.py
│   ├── schema.py        # Pydantic data contracts
│   ├── security.py      # Zero-trust sanitization pipeline
│   ├── core.py          # Execution runtime engine
│   └── cli.py           # Rich-based terminal UI
├── tests/
│   └── test_engine.py   # Test suite
├── agent.brompt.yaml    # Runtime policy manifest
├── pyproject.toml
└── README.md
```

## Configuration

Runtime behavior is governed by `agent.brompt.yaml`:

```yaml
metadata:
  name: "ProductionAgentEngine"
  version: "1.0.0-alpha"
  environment: "production"

security_policy:
  isolation_level: "ZERO_TRUST"
  sanitize_inputs: true
  max_payload_size_kb: 64

memory_strategy:
  paging_mode: "VIRTUAL_STATE_O1"
  max_history_turns: 3
```

## License

MIT

```
     ███████████                                                █████   
    ░░███░░░░░███                                              ░░███    
     ░███    ░███ ████████   ██████  █████████████   ████████  ███████  
     ░██████████ ░░███░░███ ███░░███░░███░░███░░███ ░░███░░███░░░███░   
     ░███░░░░░███ ░███ ░░░ ░███ ░███ ░███ ░███ ░███  ░███ ░███  ░███    
     ░███    ░███ ░███     ░███ ░███ ░███ ░███ ░███  ░███ ░███  ░███ ███
     ███████████  █████    ░░██████  █████░███ █████ ░███████   ░░█████ 
    ░░░░░░░░░░░  ░░░░░      ░░░░░░  ░░░░░ ░░░ ░░░░░  ░███░░░     ░░░░░  
                                                 ░███               
                                                 █████              
                                                ░░░░░               
```

---

# 🛡️ Brompt Engine

## 1. System Architecture Overview

The **Brompt Engine** addresses the fundamental limitations of modern LLM agents: non-deterministic execution paths and linear context drift (`O(N)` token growth). It acts as an execution middleware positioning itself between host application environments and upstream model endpoints.

```text
[ Application Payload ]
         │
         ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                       BROMPT RUNTIME                        │
 │                                                             │
 │   1. Security Ingress Pipeline (Pattern Sanitize / AST)    │
 │   2. Virtual State Paging Engine (O(1) Memory State)       │
 │   3. Schema Validator & JSON Contract Enforcement           │
 └─────────────────────────────────────────────────────────────┘
         │
         ▼
[ Upstream LLM Provider ]
```

### Core Architecture Pillars:

| Pillar | Description |
|---|---|
| **Zero-Trust Guardrails** | Deterministic regex and pattern matching prevent jailbreaks, prompt overrides, and payload leakage |
| **Virtual State Memory** | `O(1)` bounded state dictionary replaces raw message concatenation — fixed memory regardless of session depth |
| **Structured Type Contracts** | Pydantic v2 schema validation guarantees typed, programmatic outputs for downstream tooling |

---

## 2. Repository Layout

```text
Brompt/
├── .github/
│   └── workflows/
│       └── ci.yml                 # GitHub Actions CI/CD Pipeline
├── src/
│   └── brompt/
│       ├── __init__.py
│       ├── schema.py              # Data Models & System Schemas
│       ├── security.py            # Guardrails & Ingress Filtering
│       ├── memory.py              # Virtual State Engine (O(1) Paging)
│       ├── core.py                # Main Execution Runtime Engine
│       └── cli.py                 # Rich Terminal User Interface (TUI)
├── tests/
│   ├── test_core.py               # Core Runtime Unit Tests
│   ├── test_security.py           # Security Filter Unit Tests
│   └── test_memory.py             # Memory Engine Unit Tests
├── agent.brompt.yaml              # Declarative Runtime Manifest
├── pyproject.toml                 # Package Configuration & Dependencies
└── README.md                      # Technical Specification
```

---

## 3. Configuration Manifest

Runtime behavior is governed by `agent.brompt.yaml`:

```yaml
metadata:
  name: "ProductionAgentEngine"
  version: "0.1.0-alpha"
  environment: "production"

security_policy:
  isolation_level: "ZERO_TRUST"
  sanitize_inputs: true
  max_payload_size_kb: 64

memory_strategy:
  paging_mode: "VIRTUAL_STATE_O1"
  max_history_turns: 3

schema_validation:
  strict_mode: true
```

---

## 4. Quick Start

```bash
# Clone
git clone https://github.com/sh0-dax/Brompt.git
cd Brompt

# Install
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest -v

# Launch CLI
brompt
```

---

## 5. API Reference

### `BromptEngine(config_path)`

Core runtime entry point. Loads YAML manifest and initializes all subsystems.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `config_path` | `str` | `"agent.brompt.yaml"` | Path to runtime manifest |

**Methods:**

- `execute(user_query, context=None) → ExecutionResult` — Processes a query through the full guardrail pipeline.

### `SecurityEngine.sanitize(text)`

Static method. Validates input against adversarial patterns. Raises `ValueError` on violation.

### `MemoryManager(max_turns)`

Virtual state engine for `O(1)` context management.

| Method | Returns | Description |
|---|---|---|
| `update_state(key, value)` | `None` | Sets a key in the state dictionary |
| `get_state()` | `Dict[str, Any]` | Returns a copy of the current state |
| `clear()` | `None` | Flushes all state |

---

## 6. CI/CD Pipeline

GitHub Actions runs tests on every push/PR across Python 3.10–3.13:

```yaml
matrix:
  python-version: ["3.10", "3.11", "3.12", "3.13"]
```

---

## 7. License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <sub>Built by <b>SH ÂZZOUZ</b> — sh0-dax</sub>
</p>

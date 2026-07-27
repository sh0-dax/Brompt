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

**Performance Note:** While theoretical complexity is `O(N)` due to input sanitization scanning, strict payload bounds (64KB max) make performance effectively near-constant `O(1)` in practice.

```text
[ Application Payload ]
         │
         ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                       BROMPT RUNTIME                        │
 │                                                             │
 │   1. Security Ingress Pipeline (Pattern Sanitize / Validate)│
 │   2. Bounded State Management Engine (Fixed-Size Context)   │
 │   3. Schema Validator & JSON Contract Enforcement           │
 └─────────────────────────────────────────────────────────────┘
         │
         ▼
[ Upstream LLM Provider ]
```

### Core Architecture Pillars:

| Pillar | Description |
|---|---|
| **Defense in Depth Security** | Multi-layered protection with input sanitization, pattern matching, payload size limits, and planned rate limiting & audit logging |
| **Bounded State Management** | Thread-safe state dictionary with fixed-size context tracking — no raw message accumulation across turns |
| **Structured Type Contracts** | Pydantic v2 schema validation guarantees typed, programmatic outputs for downstream tooling |
| **Modern Type Safety** | Updated Python 3.10+ type annotations for better IDE support and static analysis |

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
│       ├── memory.py              # Bounded State Manager (Thread-Safe)
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

Static method. Validates input against adversarial patterns. Raises `SecurityViolationError` or `ValueError` on violation.

### `MemoryManager(max_turns)`

Bounded state manager for fixed-size context tracking.

| Method | Returns | Description |
|---|---|---|
| `update_state(key, value)` | `None` | Thread-safe state update |
| `get_state()` | `Dict[str, Any]` | Returns a snapshot copy of the current state |
| `clear()` | `None` | Thread-safe state flush |

---

## 6. CI/CD Pipeline

GitHub Actions runs tests on every push/PR across Python 3.10–3.13:

```yaml
matrix:
  python-version: ["3.10", "3.11", "3.12", "3.13"]
```

---

## 7. Production Readiness

**Current Status: Alpha** — This engine is in active development and requires the following before production deployment:

- ✅ Security guardrails with input sanitization
- ✅ Bounded memory management
- ✅ Schema validation
- ⚠️ **Pending:** Rate limiting implementation
- ⚠️ **Pending:** Security audit logging
- ⚠️ **Pending:** Output sanitization layer
- ⚠️ **Pending:** Async/await support for high concurrency

---

## 8. License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <sub>Built by ❤️ <b>SH ÂZZOUZ</b> — sh0-dax</sub>
</p>

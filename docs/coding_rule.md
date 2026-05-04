# Coding Rules

## Test Priority: Monkeypatch

When writing unit tests, **prefer monkeypatch (`pytest.MonkeyPatch`)** over mocking libraries (e.g. `unittest.mock`).

**Why monkeypatch:**
- No extra imports or dependencies
- Direct, readable, explicit
- Works well with pytest's fixture system
- Reduced abstraction overhead

**How to use monkeypatch:**

```python
def test_something(monkeypatch):
    # Replace a function/class at import time
    monkeypatch.setattr("email.message_from_bytes", mock_message_from_bytes)

    # Replace a module-level attribute
    monkeypatch.setattr("os.path.dirname", lambda p: "/tmp")

    # Replace a method on an instance
    monkeypatch.setattr(obj, "method_name", mock_method)
```

**Rule of thumb:**
- If you can use `monkeypatch.setattr` for an attribute/function, prefer it over `Mock()` objects
- Only use `unittest.mock.Mock` / `unittest.mock.patch` when monkeypatch is too awkward (e.g. constant setup/teardown, complex spy scenarios)

## Pre-commit Rule

Before committing, **must run lint + test** locally:

```bash
uv run ruff check scripts/ && uv run pytest test/
```

No exceptions. Catch issues before they reach the repo.

## Other Test Conventions

- Test file naming: `test_<script_name>.py` in `test/` directory
- One test class per script: `Test<ScriptName>`
- Test functions: `test_<behavior>_<expected_outcome>`
- Fixtures for shared setup (use pytest fixtures)
- All scripts must pass linting before committing
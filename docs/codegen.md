# Type-Safe Smalltalk Codegen

`gemstone-codegen` turns registered Python `Protocol` classes into concrete
`TypedOop` wrappers. The generated files are ordinary Python modules, so IDEs
can autocomplete methods and your application code no longer has to spell the
same Smalltalk strings at every call site.

## Install

The generator ships with `gemstone-py`:

```bash
python -m pip install gemstone-py
gemstone-codegen --help
```

For source checkouts:

```bash
python -m pip install -e ".[examples,dev]"
python -m gemstone_py.codegen --help
```

## Define Protocols

Create a module with one or more `@gemstone_class(...)` protocols:

```python
from typing import Protocol
from gemstone_py import gemstone_class, gemstone_selector

@gemstone_class("OkzBooking", async_=True)
class OkzBookingProto(Protocol):
    status: str

    @classmethod
    @gemstone_selector("findById:")
    def find_by_id(cls, booking_id: str) -> "OkzBookingProto":
        ...

    def mark_paid(self, at_posix_seconds: int) -> None:
        ...

    def yourself(self) -> "OkzBookingProto":
        ...

    @gemstone_selector("transferTo:byUserId:")
    def transfer(self, user_id: int, by_user_id: int) -> None:
        ...
```

`async_=True` asks the generator to emit both sync and async wrappers.

## Generate Wrappers

Run the generator from the repository or application root:

```bash
gemstone-codegen \
  --module examples.typed_access.codegen_demo.models \
  --output examples/typed_access/codegen_demo/generated
```

The output is meant to be checked in. That keeps reviews, editor indexing, and
type checking predictable:

```bash
git add examples/typed_access/codegen_demo/generated
```

Use `--check` in CI or pre-commit hooks to catch drift:

```bash
gemstone-codegen \
  --module examples.typed_access.codegen_demo.models \
  --output examples/typed_access/codegen_demo/generated \
  --check
```

The repository CI runs the same check through:

```bash
./scripts/check_codegen.sh
```

If your application uses `pre-commit`, it can consume the packaged hook:

```yaml
repos:
  - repo: https://github.com/unicompute/gemstone-py
    rev: main
    hooks:
      - id: gemstone-codegen-check
```

## Selector Mapping

Default mapping is intentionally small:

| Python shape | Generated Smalltalk selector |
| --- | --- |
| `status` | `status` |
| `find_by_id(id)` | `findById:` |
| `mark_paid(at)` | `markPaid:` |
| `transfer_to(user_id, by_user_id)` | `transferTo:byUserId:` |

For selectors that do not map cleanly, use `@gemstone_selector(...)`. The
explicit selector must have the same keyword count as the Python method has
arguments.

## Return Mapping

The generator uses simple Protocol annotations to choose the send path and the
generated Python return type:

| Protocol return annotation | Generated behaviour |
| --- | --- |
| no annotation | `perform_value(...)` / `session.eval(...)`, returns `Any` |
| `None` | sends the message and returns `None` |
| same Protocol class, wrapper class, or `Self` | uses `perform_oop(...)` or `execute_oop(...)` and wraps the returned OOP |
| simple builtins such as `str`, `int`, `float`, `bool` | value send with that return annotation |

That means this method returns another typed wrapper:

```python
def yourself(self) -> "OkzBookingProto":
    ...
```

while this method is treated as a mutating command:

```python
def mark_paid(self, at_posix_seconds: int) -> None:
    ...
```

## Sync Usage

Generated class-side methods take a session and build the Smalltalk source:

```python
from gemstone_py import GemStoneConfig, GemStoneSession
from examples.typed_access.codegen_demo.generated import OkzBooking

with GemStoneSession(config=GemStoneConfig.from_env()) as session:
    booking = OkzBooking.find_by_id(session, "B-1001")
    print(booking.status)
    booking.mark_paid(1_779_912_000)
    same_booking = booking.yourself()
```

That class-side call evaluates:

```smalltalk
OkzBooking findById: 'B-1001'
```

Instance methods call `perform_value(...)` for value returns and
`perform_oop(...)` for self-typed wrapper returns through the session
associated with the returned `TypedOop`.

## Async Usage

When the Protocol is registered with `async_=True`, the generator also emits an
`Async...` wrapper:

```python
from fastapi import Depends, FastAPI
from gemstone_py import GemStoneConfig
from gemstone_py.aio import AsyncSession
from gemstone_py.aio.fastapi import session_dependency
from examples.typed_access.codegen_demo.generated import AsyncOkzBooking

app = FastAPI()
get_gemstone = session_dependency(config=GemStoneConfig.from_env(require_credentials=False))

@app.get("/bookings/{booking_id}")
async def booking_status(
    booking_id: str,
    session: AsyncSession = Depends(get_gemstone),
) -> dict[str, str]:
    booking = await AsyncOkzBooking.find_by_id(session, booking_id)
    return {"status": str(await booking.status())}
```

## Current Scope

The first generator pass handles:

- annotated fields and `@property` methods as no-argument sends
- instance methods as `perform_value(...)` or `perform_oop(...)` sends based on
  return annotations
- class methods as class-side Smalltalk source strings
- self-returning class and instance methods as wrapped `TypedOop` results
- string, integer, float, boolean, and `None` literals in class-side calls
- explicit selector overrides with `@gemstone_selector(...)`
- checked-in sync and async generated modules plus CI/pre-commit drift checks
- an opt-in live smoke test for generated wrappers against GemStone `Date`

It does not marshal arbitrary Python objects into class-side source literals or
replace hand-written Smalltalk for complex queries. Use it for method-shaped
object access and keep raw `session.eval(...)` or `SmalltalkBridge` calls where
a full Smalltalk expression is clearer.

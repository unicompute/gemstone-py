# Type-Safe Smalltalk Codegen Demo

This example shows the Protocol-to-wrapper workflow:

1. define a Python `Protocol` with `@gemstone_class(...)`
2. pin ambiguous selectors with `@gemstone_selector(...)`
3. run `gemstone-codegen`
4. import the generated wrapper from application code

Start with the offline preview. It writes generated files to a temporary
directory and prints the concrete follow-up commands, so it is safe to run
before changing checked-in generated files:

```bash
python -m examples.typed_access.codegen_demo.preview
python -m examples.typed_access.codegen_demo.preview --show-source
```

Generate wrappers from the repository root:

```bash
gemstone-codegen \
  --module examples.typed_access.codegen_demo.models \
  --output examples/typed_access/codegen_demo/generated \
  --clean
```

Check that committed wrappers are current:

```bash
gemstone-codegen \
  --module examples.typed_access.codegen_demo.models \
  --output examples/typed_access/codegen_demo/generated \
  --check
```

The generated package includes runtime `.py` modules, matching `.pyi` stubs,
and `py.typed` so editors and type checkers can read the wrapper contract.

The companion VS Code workbench can drive the same workflow visually. Open
`GemStone: Open Codegen Explorer`, connect to the configured database explorer,
select `OkzBooking` and `OkzCustomer`, preview wrappers, diff them against this
`generated/` package, and save the selection as a reusable mapping. This
example includes a starter mapping:

```text
examples/typed_access/codegen_demo/codegen-workbench.example.json
```

Use it as a concrete checklist for the live selection:

| GemStone class | Class-side selectors | Instance selectors |
| --- | --- | --- |
| `OkzBooking` | `findById:` | `status`, `customer`, `markPaid:`, `transferTo:byUserId:`, `yourself` |
| `OkzCustomer` | none | `name`, `yourself` |

Run the generated-wrapper FastAPI demo:

```bash
python -m examples.typed_access.codegen_demo.run --reload
```

Then open:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/bookings/B-1001
```

The booking endpoint needs GemStone credentials and a reachable stone because
it calls `OkzBooking findById:` through the generated async wrapper.

Probe the generated sync wrapper directly against a live stone:

```bash
export GS_STONE_NAME=gs64stone
export GS_USERNAME=DataCurator
export GS_PASSWORD=swordfish
python -m examples.typed_access.codegen_demo.live_probe --booking-id B-1001
```

Use the generated sync wrapper:

```python
from gemstone_py import GemStoneConfig, GemStoneSession
from examples.typed_access.codegen_demo.generated import OkzBooking

with GemStoneSession(config=GemStoneConfig.from_env()) as session:
    booking = OkzBooking.find_by_id(session, "B-1001")
    print(booking.status)
    booking.mark_paid(1_779_912_000)
    same_booking = booking.yourself()
    customer = booking.customer()
    print(customer.name)
```

Use the generated async wrapper in a FastAPI handler:

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

The generated class-side method builds:

```smalltalk
OkzBooking findById: 'B-1001'
```

Instance methods use `perform_value(...)` through the typed OOP session:

```python
booking.mark_paid(1_779_912_000)  # Smalltalk selector markPaid:
booking.yourself()                # wraps the returned OOP as OkzBooking
booking.customer()                # wraps the returned OOP as OkzCustomer
booking.transfer(42, 7)           # Smalltalk selector transferTo:byUserId:
```

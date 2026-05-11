# Type-Safe Smalltalk Codegen Demo

This example shows the Protocol-to-wrapper workflow:

1. define a Python `Protocol` with `@gemstone_class(...)`
2. pin ambiguous selectors with `@gemstone_selector(...)`
3. run `gemstone-codegen`
4. import the generated wrapper from application code

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

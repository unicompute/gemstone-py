# Adding a Framework Adapter

Use `gemstone_py.web_core` for request lifetime and transaction decisions.
Adapters should stay thin: translate the framework's request hooks into
`RequestScope` or `AsyncRequestScope`, then expose one helper that returns the
current request session.

## Sync Framework Shape

```python
from gemstone_py import GemStoneConfig, RequestScope, TransactionPolicy
from gemstone_py.session_providers import GemStoneSessionPool

pool = GemStoneSessionPool(maxsize=4, config=GemStoneConfig.from_env())

def begin_request(request):
    request.gemstone_scope = RequestScope(
        session_provider=pool,
        transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
    )

def current_session(request):
    return request.gemstone_scope.session()

def end_request(request, exc=None, response_status=None):
    request.gemstone_scope.finalize(exc, response_status=response_status)
```

The scope commits on successful responses, aborts on exceptions or server-error
status codes, and releases pooled sessions with the correct `clean`/`discard`
flags.

## Async Framework Shape

```python
from gemstone_py import AsyncRequestScope, GemStoneConfig, TransactionPolicy
from gemstone_py.aio.pool import AsyncSessionPool

pool = AsyncSessionPool(maxsize=8, config=GemStoneConfig.from_env())

async def begin_request(scope):
    scope["gemstone_scope"] = AsyncRequestScope(
        session_provider=pool,
        transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
    )
    scope["gemstone_session"] = await scope["gemstone_scope"].session()

async def end_request(scope, exc=None, response_status=None):
    await scope["gemstone_scope"].finalize(exc, response_status=response_status)
```

## Existing Adapters

| Framework | Module | Pattern |
| --- | --- | --- |
| Flask | `gemstone_py.frameworks.flask` | request-local sync session |
| Django | `gemstone_py.frameworks.django` | middleware-managed sync session |
| FastAPI | `gemstone_py.aio.fastapi` | async dependency and ASGI middleware |
| Litestar | `gemstone_py.aio.litestar` | async dependency and ASGI middleware |

Keep optional framework imports inside app/example code or function bodies, not
at package import time. The adapter module should remain importable in a plain
`gemstone-py` installation.

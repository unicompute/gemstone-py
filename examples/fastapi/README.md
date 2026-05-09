# FastAPI Example

Install FastAPI separately, configure GemStone with the usual `GS_*`
environment variables, then run:

```bash
uvicorn examples.fastapi.app:app --reload
```

The example uses `gemstone_py.aio.fastapi.session_dependency`, which opens one
`AsyncSession` per request, commits successful handlers, aborts failed handlers,
and logs out at the end of the request.

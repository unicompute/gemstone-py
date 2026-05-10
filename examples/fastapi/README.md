# FastAPI Example

Install the repository example dependencies, configure GemStone with the usual
`GS_*` environment variables, then run:

```bash
python -m pip install -e ".[examples]"
python -m examples.fastapi.run --reload
```

For an installed package rather than a repository checkout:

```bash
python -m pip install "gemstone-py[fastapi]"
gemstone-fastapi-example --reload
```

Open `http://127.0.0.1:8000/` for the example index,
`http://127.0.0.1:8000/docs` for the interactive FastAPI docs, or
`http://127.0.0.1:8000/health/gemstone` for the GemStone health check.

## Verify

With the server running, test it from a second terminal:

```bash
curl -i http://127.0.0.1:8000/
```

Expected status:

```text
HTTP/1.1 200 OK
```

The body should include:

```json
{"name":"gemstone-py FastAPI example","endpoints":{"health":"/health/gemstone","docs":"/docs","openapi":"/openapi.json"}}
```

Then test the GemStone endpoint:

```bash
curl -i http://127.0.0.1:8000/health/gemstone
```

Expected when GemStone credentials and the stone are reachable:

```json
{"result":7}
```

You can also open these URLs in a browser:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/health/gemstone
```

The example uses `gemstone_py.aio.fastapi.session_dependency`, which opens one
`AsyncSession` per request, commits successful handlers, aborts failed handlers,
and logs out at the end of the request.

For the same async surface outside a web framework, run:

```bash
python -m examples.async_features.session_root_and_collection
```

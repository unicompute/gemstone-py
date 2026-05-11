# Litestar Example

Minimal Litestar app using `gemstone_py.aio.litestar.session_dependency`.

Install the optional dependencies from a source checkout:

```bash
python -m pip install -e ".[examples]"
```

Run the app:

```bash
python -m examples.litestar.run --reload
```

Then test it from a second terminal:

```bash
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/health/gemstone
```

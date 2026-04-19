"""
ObjectLog viewer in Flask.

A simple web UI for browsing, inspecting, and clearing the GemStone
ObjectLog.  Useful during development and debugging.

Routes
------
    GET  /              — redirect to /objectlog
    GET  /objectlog     — list all ObjectLogEntry records
    GET  /entry/<idx>   — inspect a single entry by index
    GET  /clear         — clear the log and redirect back
    GET  /info          — environment info (text/plain)

Run
---
    cd examples/flask/object_inspector
    python objectlog_app.py

Then open http://localhost:5001/objectlog in a browser.

Mount point
-----------
The app is relocatable.  If you mount it under a prefix with a WSGI
dispatcher or Flask blueprints, set SCRIPT_NAME in the WSGI environ and
Flask handles url_for() correctly.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import os
import sys

from flask import Flask, render_template_string, redirect, url_for, abort

from gemstone_py.example_support import example_config
from gemstone_py.objectlog import ObjectLog, ObjectLogEntry

app = Flask(__name__)
_log = ObjectLog(config=example_config())


# ---------------------------------------------------------------------------
# Templates (inline so the app is self-contained — no templates/ directory
# needed for a debugging tool)
# ---------------------------------------------------------------------------

_BASE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{{ title }}</title>
  <style>
    body { font-family: monospace; margin: 2em; }
    nav a { margin-right: 1em; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; }
    th { background: #eee; }
    tr:hover { background: #f9f9f9; }
    .TRACE { color: #999; }
    .DEBUG { color: #66a; }
    .INFO  { color: #090; }
    .WARN  { color: #a60; }
    .ERROR { color: #c00; font-weight: bold; }
    .FATAL { color: #900; font-weight: bold; background: #fee; }
    pre { background: #f4f4f4; padding: 1em; overflow-x: auto; }
  </style>
</head>
<body>
<nav>
  <a href="{{ url_for('index') }}">ObjectLog</a>
  <a href="{{ url_for('clear') }}">Clear Log</a>
  <a href="{{ url_for('info') }}">Info</a>
</nav>
<hr>
{% block content %}{% endblock %}
</body>
</html>"""

_LOG_TMPL = _BASE.replace(
    "{% block content %}{% endblock %}",
    """
<h2>ObjectLog ({{ entries|length }} entries)</h2>
{% if entries %}
<table>
  <tr><th>#</th><th>Level</th><th>Timestamp</th><th>PID</th><th>Label</th><th>Object</th></tr>
  {% for e in entries %}
  <tr class="{{ e.level_name.upper() }}">
    <td><a href="{{ url_for('entry', idx=e.index) }}">{{ e.index }}</a></td>
    <td>{{ e.level_name.upper() }}</td>
    <td>{{ e.timestamp }}</td>
    <td>{{ e.pid }}</td>
    <td>{{ e.label }}</td>
    <td>{{ e.object_repr if e.object_repr != 'nil' else '' }}</td>
  </tr>
  {% endfor %}
</table>
{% else %}
<p>The ObjectLog is empty.</p>
{% endif %}
""")

_ENTRY_TMPL = _BASE.replace(
    "{% block content %}{% endblock %}",
    """
<h2>ObjectLogEntry #{{ entry.index }}</h2>
<table>
  <tr><th>Field</th><th>Value</th></tr>
  <tr><td>level</td><td class="{{ entry.level_name.upper() }}">{{ entry.level_name.upper() }}</td></tr>
  <tr><td>priority</td><td>{{ entry.priority }}</td></tr>
  <tr><td>label</td><td>{{ entry.label }}</td></tr>
  <tr><td>timestamp</td><td>{{ entry.timestamp }}</td></tr>
  <tr><td>pid</td><td>{{ entry.pid }}</td></tr>
  <tr><td>object</td><td><pre>{{ entry.object_repr }}</pre></td></tr>
  {% if entry.tagged %}
  <tr><td>tag</td><td>{{ entry.tag }}</td></tr>
  {% endif %}
</table>
<p><a href="{{ url_for('index') }}">← Back to log</a></p>
""")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get('/')
def root():
    return redirect(url_for('index'))


@app.get('/objectlog')
def index():
    entries = _log.entries()
    return render_template_string(_LOG_TMPL, title='ObjectLog', entries=entries)


@app.get('/entry/<int:idx>')
def entry(idx: int):
    entries = _log.entries()
    matches = [e for e in entries if e.index == idx]
    if not matches:
        abort(404, f"No ObjectLogEntry at index {idx}")
    return render_template_string(_ENTRY_TMPL, title=f'Entry #{idx}', entry=matches[0])


@app.get('/clear')
def clear():
    _log.clear()
    return redirect(url_for('index'))


@app.get('/info')
def info():
    import platform
    body = (
        f"Python       {sys.version.split()[0]}\n"
        f"Platform     {platform.platform()}\n"
        f"ObjectLog    gemstone-py ObjectLog viewer\n"
    )
    return body, 200, {'Content-Type': 'text/plain'}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"ObjectLog viewer at http://localhost:{port}/objectlog")
    app.run(debug=True, port=port)

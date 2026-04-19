"""
Port of sinatra/maglev_sessions/msessions.rb → Flask

Shows how to use the GemStone-backed session store.
Each page hit increments a counter stored in GemStone and lists
all active sessions.

Run:
    pip install flask
    python msessions.py
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

from flask import Flask, session, render_template_string

import gemstone_py as gemstone
from examples.flask.sessions.gemstone_sessions import (
    GS_SESSIONS_KEY,
    GemStoneSessionInterface,
)
from gemstone_py.persistent_root import PersistentRoot

app = Flask(__name__)
app.secret_key = 'gemstone-sessions-secret'
app.session_interface = GemStoneSessionInterface()
gemstone.install_flask_request_session(app)


TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>GemStone Sessions</title></head>
<body>
  <h2>GemStone-backed Flask Sessions</h2>
  <p>Current session counter: <strong>{{ counter }}</strong></p>
  <h3>All active sessions in GemStone:</h3>
  <ul>
    {% for sid, data in sessions.items() %}
      <li><code>{{ sid[:8] }}…</code> → {{ data }}</li>
    {% else %}
      <li>(none)</li>
    {% endfor %}
  </ul>
  <p><a href="/">Refresh</a></p>
</body>
</html>
"""


def _plain(value):
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    keys = getattr(value, 'keys', None)
    if callable(keys) and hasattr(value, '__getitem__'):
        return {str(k): _plain(value[k]) for k in value.keys()}
    return value


@app.get('/')
def index():
    session['counter'] = session.get('counter', 0) + 1

    # Read all sessions from GemStone for display
    all_sessions = {}
    try:
        with gemstone.session_scope() as s:
            root = PersistentRoot(s)
            if GS_SESSIONS_KEY in root:
                store = root[GS_SESSIONS_KEY]
                for sid in store.keys():
                    all_sessions[sid] = _plain(store[sid])
    except Exception as e:
        all_sessions = {'error': str(e)}

    return render_template_string(
        TEMPLATE,
        counter=session['counter'],
        sessions=all_sessions,
    )


if __name__ == '__main__':
    app.run(debug=True, port=4568)

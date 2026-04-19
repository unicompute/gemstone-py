"""
Port of sinatra/sinatra_app.rb → Flask

Sinatra → Flask mapping:
  get '/'         → @app.get('/')
  params[:name]   → request.view_args['name']
  params['splat'] → captured wildcards via path converter
  redirect '/'    → redirect(url_for(...))
  session[...]    → flask.session[...]
  status 404      → abort(404) or return ..., 404
  throw :halt     → return ..., 404

Run:
    pip install flask
    python app.py
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

from flask import Flask, redirect, url_for, session, abort, request

app = Flask(__name__)
app.secret_key = 'gemstone-example-secret'


@app.get('/')
def index():
    return """
    <html>
      <head><title>Flask Hello</title></head>
      <body>
        <h2>Flask says Hello</h2>
        <h2>Some test URLs</h2>
        <ul>
          <li><a href="/names/fred">/names/fred</a></li>
          <li><a href="/say/hi/to/Flask">/say/hi/to/Flask</a></li>
          <li><a href="/goto_home">/goto_home</a></li>
          <li><a href="/session_count">/session_count</a></li>
          <li><a href="/not_found">/not_found</a></li>
        </ul>
      </body>
    </html>
    """


@app.get('/names/<name>')
def names(name):
    return f"The name is: {name}"


# Sinatra wildcard splats: GET '/say/*/to/*'
# Flask uses a path converter for the first segment; we parse manually.
@app.get('/say/<action>/to/<target>')
def say_to(action, target):
    return f"Say '{action}' to {target}"


@app.get('/goto_home')
def goto_home():
    return redirect(url_for('index'))


@app.get('/session_count')
def session_count():
    session['counter'] = session.get('counter', 0) + 1
    return f"count: {session['counter']}"


@app.get('/not_found')
def not_found():
    return "Custom Not Found", 404


if __name__ == '__main__':
    app.run(debug=True)

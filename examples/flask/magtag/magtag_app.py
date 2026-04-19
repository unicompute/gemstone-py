"""
MagTag: a minimal Twitter-like web app backed by GemStone.

Routes
------
    GET  /               → redirect to /timeline
    GET  /timeline       → current user's timeline (requires login)
    GET  /signup         → signup form
    POST /signup         → create account
    GET  /login          → login form
    POST /login          → authenticate
    GET  /logout         → clear session
    POST /tweet          → post a tweet (requires login)
    GET  /user/<name>    → public profile: tweets + followers

Run:
    pip install flask
    python3 magtag_app.py
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import platform

import gemstone_py as gemstone
from flask import (Flask, render_template_string, redirect, url_for,
                   request, session, flash, abort)
from examples.flask.magtag.models import User, Tweet, UserException

app = Flask(__name__)
app.secret_key = 'magtag-gemstone-secret'
gemstone.install_flask_request_session(app)


# ---------------------------------------------------------------------------
# Inline templates (self-contained, no separate files needed)
# ---------------------------------------------------------------------------

_LAYOUT = """
<!DOCTYPE html>
<html>
<head>
  <title>MagTag</title>
  <style>
    body { font-family: sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px; }
    nav  { margin-bottom: 20px; }
    nav a { margin-right: 12px; }
    .tweet  { border-bottom: 1px solid #ddd; padding: 8px 0; }
    .author { font-weight: bold; }
    .time   { color: #888; font-size: 0.85em; }
    .flash  { background: #fffbe6; border: 1px solid #ffe58f; padding: 8px; margin-bottom: 12px; }
    .error  { background: #fff2f0; border: 1px solid #ffccc7; padding: 8px; margin-bottom: 12px; }
  </style>
</head>
<body>
  <h2><a href="/" style="text-decoration:none">MagTag</a></h2>
  <nav>
    {% if current_user %}
      Logged in as <strong>{{ current_user }}</strong> |
      <a href="{{ url_for('timeline') }}">Timeline</a> |
      <a href="{{ url_for('logout') }}">Logout</a>
    {% else %}
      <a href="{{ url_for('login_page') }}">Login</a> |
      <a href="{{ url_for('signup_page') }}">Sign up</a>
    {% endif %}
  </nav>
  {% for msg in get_flashed_messages() %}
    <div class="flash">{{ msg }}</div>
  {% endfor %}
  {% block body %}{% endblock %}
</body>
</html>
"""

_TIMELINE = _LAYOUT.replace('{% block body %}{% endblock %}', """
{% block body %}
  <h3>Your timeline</h3>
  <form method="post" action="{{ url_for('post_tweet') }}" style="margin-bottom:16px">
    <input name="text" placeholder="What's happening?" style="width:70%">
    <button type="submit">Tweet</button>
  </form>
  {% if tweets %}
    {% for tw in tweets %}
      <div class="tweet">
        <span class="author">{{ tw.author }}</span>:
        {{ tw.text }}
        <span class="time"> · {{ tw.age }}</span>
      </div>
    {% endfor %}
  {% else %}
    <p>No tweets yet. Follow someone or post your own!</p>
  {% endif %}
{% endblock %}
""")

_PROFILE = _LAYOUT.replace('{% block body %}{% endblock %}', """
{% block body %}
  <h3>{{ user.name }}</h3>
  <p>{{ user.num_tweets() }} tweets · {{ user.num_followers() }} followers ·
     following {{ user.num_following() }}</p>
  {% if current_user and current_user != user.name %}
    <form method="post" action="{{ url_for('follow', name=user.name) }}">
      <button type="submit">Follow</button>
    </form>
  {% endif %}
  <hr>
  {% for tw in user.tweets %}
    <div class="tweet">
      {{ tw.text }}
      <span class="time"> · {{ tw.twitterize_date() }}</span>
    </div>
  {% endfor %}
{% endblock %}
""")

_FORM = _LAYOUT.replace('{% block body %}{% endblock %}', """
{% block body %}
  <h3>{{ title }}</h3>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="post">
    <p><label>Username<br><input name="username"></label></p>
    <p><label>Password<br><input name="password" type="password"></label></p>
    {% if confirm %}
    <p><label>Confirm password<br><input name="confirm_pw" type="password"></label></p>
    {% endif %}
    <button type="submit">{{ title }}</button>
  </form>
{% endblock %}
""")


def _ctx():
    return dict(current_user=session.get('username'))


def _tweet_view(author: str, tweet: Tweet) -> dict:
    return {
        'author': tweet.author or author,
        'text': tweet.text,
        'age': tweet.twitterize_date(),
        'date': tweet.date,
    }


def _build_demo_users() -> list[User]:
    users = [User(f'pbm{i}', f'pbm{i}') for i in range(3)]
    by_name = {user.name: user for user in users}

    for user in users:
        for other in users:
            if user.name == other.name:
                continue
            user._following.append(other.name)
            other._followers.append(user.name)

    for i in range(10):
        for user in users:
            tweet = Tweet(
                f"{user.name}[{i}] Hey... I'm following people!",
                author=user.name,
            )
            user._tweets.insert(0, tweet)
            for follower_name in user._followers:
                by_name[follower_name].add_timeline(tweet)

    return users


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get('/')
def root():
    return redirect(url_for('timeline'))


@app.get('/home')
@app.get('/timeline')
def timeline():
    username = session.get('username')
    if not username:
        return redirect(url_for('login_page'))
    user = User.find_by_name(username)
    if not user:
        session.clear()
        return redirect(url_for('login_page'))

    own = [_tweet_view(username, t) for t in user.tweets]
    feed = [_tweet_view('followed user', t) for t in user.timeline]
    tweets = sorted(own + feed, key=lambda tweet: tweet['date'], reverse=True)

    return render_template_string(_TIMELINE, tweets=tweets, **_ctx())


@app.get('/signup')
def signup_page():
    return render_template_string(_FORM, title='Sign up', confirm=True, error=None, **_ctx())


@app.post('/signup')
def signup():
    username   = request.form.get('username', '').strip()
    password   = request.form.get('password', '')
    confirm_pw = request.form.get('confirm_pw', '')
    try:
        user = User.signup(username, password, confirm_pw)
        session['username'] = user.name
        flash(f"Welcome, {user.name}!")
        return redirect(url_for('timeline'))
    except (UserException, ValueError) as e:
        return render_template_string(_FORM, title='Sign up', confirm=True,
                                      error=str(e), **_ctx())


@app.get('/login')
def login_page():
    return render_template_string(_FORM, title='Login', confirm=False, error=None, **_ctx())


@app.post('/login')
def login():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    user = User.find_by_name(username)
    if user and user.login(password):
        session['username'] = user.name
        return redirect(url_for('timeline'))
    return render_template_string(_FORM, title='Login', confirm=False,
                                  error='Invalid username or password.', **_ctx())


@app.get('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


@app.get('/setup')
def setup():
    users = _build_demo_users()
    User._rewrite_records([user._to_record() for user in users])

    flash("Setup done! Login with user: pbm0 password: pbm0")
    return redirect(url_for('login_page'))


@app.get('/debug')
def debug():
    users = User.all()
    return render_template_string(
        _LAYOUT.replace('{% block body %}{% endblock %}', """
{% block body %}
  <h3>Session</h3>
  <pre>{{ session_data }}</pre>
  <h3>Users</h3>
  <ul>
    {% for user in users %}
      <li>{{ user.name }} (tweets={{ user.num_tweets() }}, followers={{ user.num_followers() }})</li>
    {% else %}
      <li>(none)</li>
    {% endfor %}
  </ul>
{% endblock %}
"""),
        session_data=dict(session),
        users=users,
        **_ctx(),
    )


@app.get('/info')
def info():
    body = (
        f"Python       {sys.version.split()[0]}\n"
        f"Platform     {platform.platform()}\n"
        f"Flask        MagTag example\n"
    )
    return body, 200, {'Content-Type': 'text/plain'}


@app.post('/tweet')
def post_tweet():
    username = session.get('username')
    if not username:
        return redirect(url_for('login_page'))
    user = User.find_by_name(username)
    if not user:
        abort(404)
    text = request.form.get('text', request.form.get('tweet', '')).strip()
    if not text:
        flash("Tweet cannot be empty.")
    else:
        try:
            user.tweet(text)
        except ValueError as e:
            flash(str(e))
    return redirect(url_for('timeline'))


@app.get('/user/<name>')
def profile(name: str):
    user = User.find_by_name(name)
    if not user:
        abort(404)
    return render_template_string(_PROFILE, user=user, **_ctx())


@app.post('/follow/<name>')
def follow(name: str):
    username = session.get('username')
    if not username:
        return redirect(url_for('login_page'))
    me = User.find_by_name(username)
    other = User.find_by_name(name)
    if me and other:
        me.follow(other)
        flash(f"You are now following {name}.")
    return redirect(url_for('profile', name=name))


@app.errorhandler(404)
def not_found(e):
    return f"<h1>Not found</h1><p>{e}</p>", 404


if __name__ == '__main__':
    app.run(debug=True, port=4567)

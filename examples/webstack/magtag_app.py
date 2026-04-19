"""
Port of webstack/lib/magtag_app.rb → Flask

MagTag: a Twitter-like demo backed by GemStone persistence.

Sinatra → Flask mapping:
  helpers do ... end   → standalone functions + @app.context_processor
  before do ... end    → @app.before_request
  set :sessions, true  → app.secret_key + flask.session
  flash messages       → flask.flash / get_flashed_messages

Run:
    pip install flask
    python magtag_app.py
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import gemstone_py as gemstone
from examples.webstack.lib.tweet import twitterize_date
from examples.webstack.lib.user import Tweet, User, UserException

app = Flask(__name__)
app.secret_key = 'magtag-gemstone-secret'
app.jinja_env.globals['twitterize_date'] = twitterize_date
gemstone.install_flask_request_session(app)

# ---------------------------------------------------------------------------
# Before-request: load logged-in user (mirrors Sinatra `before do`)
# ---------------------------------------------------------------------------

OPEN_PATHS = {'/', '/login', '/signup', '/setup', '/debug', '/info', '/magtag.css'}


@app.before_request
def load_user():
    username = session.get('logged_in_user')
    g.logged_in_user = User.find_by_name(username) if username else None
    if username and g.logged_in_user is None:
        session.pop('logged_in_user', None)
    if (request.path not in OPEN_PATHS
            and not request.path.startswith('/static')
            and g.logged_in_user is None):
        return redirect(url_for('login'))


def _build_demo_users() -> list[User]:
    users = [User(f"pbm{i}", f"pbm{i}") for i in range(3)]
    by_name = {user.name: user for user in users}

    for user in users:
        for other in users:
            if user.name == other.name:
                continue
            user._following.append(other.name)
            other._followers.append(user.name)

    for i in range(3):
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
    if session.get('logged_in_user'):
        return redirect(url_for('home'))
    return redirect(url_for('login'))


@app.get('/home')
def home():
    return render_template('home.html', user=g.logged_in_user)


@app.post('/tweet')
def post_tweet():
    try:
        g.logged_in_user.tweet(
            request.form.get('tweet', request.form.get('text', ''))
        )
        flash('Tweet success!')
    except Exception as e:
        flash(str(e))
    return redirect(url_for('home'))


@app.get('/setup')
def setup():
    """Create three demo users who all follow each other and tweet."""
    users = _build_demo_users()
    User._rewrite_records([user._to_record() for user in users])

    flash("Setup done! Login with user: pbm0 password: pbm0")
    return redirect(url_for('login'))


@app.get('/login')
def login():
    return render_template('login.html')


@app.post('/login')
def do_login():
    user = User.find_by_name(request.form.get('username', '').strip())
    if user and user.login(request.form.get('password', '')):
        session['logged_in_user'] = user.name
        return redirect(url_for('home'))
    flash("Incorrect username or password.")
    return render_template('login.html')


@app.get('/logout')
def logout():
    session.pop('logged_in_user', None)
    return redirect(url_for('login'))


@app.get('/signup')
def signup():
    return render_template('signup.html')


@app.post('/signup')
def do_signup():
    try:
        user = User.signup(
            request.form.get('username', '').strip(),
            request.form.get('password', ''),
            request.form.get('confirmpassword'),
        )
        session['logged_in_user'] = user.name
        return redirect(url_for('home'))
    except UserException as e:
        flash(str(e))
        return render_template('signup.html')


@app.get('/info')
def info():
    from importlib.metadata import version

    return (
        f"Python {sys.version.split()[0]}\n"
        f"Flask {version('flask')}\n"
        f"MagTag GemStone port\n"
    ), 200, {'Content-Type': 'text/plain'}


@app.get('/debug')
def debug():
    return render_template('debug.html', user=g.logged_in_user,
                            session=dict(session))


if __name__ == '__main__':
    app.run(debug=True, port=4567)

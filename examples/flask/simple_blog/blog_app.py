"""
Simple blog app in Flask backed by GemStone.

Framework mapping:
  Sinatra::Base subclass  → Flask Blueprint (or plain Flask app)
  get '/posts'            → @app.get('/posts')
  post '/post'            → @app.post('/post')
  erb :blog               → render_template('blog.html')
  redirect '/posts'       → redirect(url_for('posts'))
  transaction commit      → wrapped in gemstone_model.save()

Run:
    pip install flask
    python blog_app.py
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import gemstone_py as gemstone
from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    url_for,
)
from examples.flask.simple_blog.blog import SimplePost, SimpleTag

app = Flask(__name__)
app.secret_key = 'gemstone-blog-secret'
gemstone.install_flask_request_session(app)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get('/')
def root():
    return redirect(url_for('posts'))


@app.get('/posts')
def posts():
    with gemstone.session_scope() as s:
        all_posts = SimplePost.all(session=s)
    all_posts.sort(key=lambda p: p.timestamp, reverse=True)
    return render_template('blog.html', posts=all_posts)


@app.get('/post/new')
def new_post():
    return render_template('newpost.html')


@app.post('/post')
def create_post():
    with gemstone.session_scope() as s:
        post = SimplePost.persistent_new(
            {
                'title': request.form.get('title', ''),
                'text': request.form.get('text', ''),
            },
            session=s,
        )
        tag_names = request.form.get('tags', '').split()

        for tag_name in tag_names:
            tag = (
                SimpleTag.find_by_name(tag_name, session=s)
                or SimpleTag.persistent_new(tag_name, session=s)
            )
            post.tag(tag)
            tag.save(session=s)

        post.save(session=s)

    return redirect(url_for('show_post', post_id=post.id))


@app.get('/post/<post_id>')
def show_post(post_id):
    with gemstone.session_scope() as s:
        post = SimplePost.get(post_id, session=s)
    if not post:
        abort(404)
    return render_template('post.html', post=post)


@app.get('/tag/<tag_id>')
def show_tag(tag_id):
    with gemstone.session_scope() as s:
        tag = SimpleTag.get(tag_id, session=s)
        tag_posts = SimplePost.get_many(tag.post_ids, session=s) if tag else []
    if not tag:
        abort(404)
    tag_posts.sort(key=lambda post: post.timestamp, reverse=True)
    return render_template('tag.html', tag=tag, posts=tag_posts)


@app.errorhandler(404)
def not_found(e):
    return f"<h1>Not Found</h1><p>{e}</p>", 404


@app.errorhandler(500)
def server_error(e):
    return f"<h1>Error</h1><p>{e}</p>", 500


if __name__ == '__main__':
    app.run(debug=True)

"""
Port of sinatra/sinatra_app_test.rb → pytest + Flask test client

Run:
    pip install flask pytest
    pytest test_app.py -v
"""

import pytest
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    with app.test_client() as c:
        yield c


def test_index(client):
    r = client.get('/')
    assert r.status_code == 200
    assert b'Flask says Hello' in r.data


def test_names(client):
    r = client.get('/names/fred')
    assert r.status_code == 200
    assert b'The name is: fred' in r.data


def test_wildcards(client):
    r = client.get('/say/hello/to/fred')
    assert r.status_code == 200
    assert b"Say 'hello' to fred" in r.data


def test_redirect(client):
    r = client.get('/goto_home')
    assert r.status_code == 302
    assert '/' in r.headers['Location']


def test_session_count(client):
    with client.session_transaction() as sess:
        sess['counter'] = 0

    r = client.get('/session_count')
    assert r.status_code == 200
    assert b'count: 1' in r.data


def test_not_found(client):
    r = client.get('/not_found')
    assert r.status_code == 404
    assert b'Custom Not Found' in r.data

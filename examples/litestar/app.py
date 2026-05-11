"""Minimal Litestar app using gemstone-py's async request dependency."""

from gemstone_py.litestar_example import create_app

app = create_app()

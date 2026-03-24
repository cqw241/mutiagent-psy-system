def test_app_can_import():
    from app.main import app

    assert app is not None

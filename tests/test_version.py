import yanka


def test_version_is_string() -> None:
    assert isinstance(yanka.__version__, str)
    assert yanka.__version__

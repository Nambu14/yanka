import whyline


def test_version_is_string() -> None:
    assert isinstance(whyline.__version__, str)
    assert whyline.__version__

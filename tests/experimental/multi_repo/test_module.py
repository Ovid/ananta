"""Test that the experimental module structure exists and is importable."""


def test_experimental_module_importable():
    """Experimental module should be importable."""
    import ananta.experimental

    assert ananta.experimental is not None


def test_multi_repo_module_importable():
    """Multi-repo module should be importable."""
    import ananta.experimental.multi_repo

    assert ananta.experimental.multi_repo is not None

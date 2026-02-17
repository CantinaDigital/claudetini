"""Tests that fail."""

def test_failing():
    assert 1 == 2, "This test always fails"

def test_another_failure():
    raise Exception("Intentional failure")

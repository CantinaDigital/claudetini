"""Module with quality issues."""

import os, sys, json  # Multiple imports on one line
import unused_module  # Unused import

def badly_formatted_function(x,y,z):  # No spaces after commas
    """Missing type hints."""
    if x==1:  # No spaces around operator
        return y+z
    else:
        return None  # Inconsistent return

class badlyNamedClass:  # Should be PascalCase
    def __init__(self):
        self.x = 1

    def method_without_docstring(self):
        pass

# TODO: This is a fixme that should be addressed
SECRET_KEY = "hardcoded-secret-12345"  # Security issue

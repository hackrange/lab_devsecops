"""Every lab check, one module per week of the course.

Author: Tim Rice
"""

from .registry import CHECKS  # noqa: F401
from . import week1, week2, week3, week4  # noqa: F401  (they register themselves)

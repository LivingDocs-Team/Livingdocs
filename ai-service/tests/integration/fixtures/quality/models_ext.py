import typing

from django.db import models

T = typing.TypeVar("T")


class Order(models.Model):
    """Order stored in the database."""
    code: str = "x"


class Box(typing.Generic[T]):
    pass

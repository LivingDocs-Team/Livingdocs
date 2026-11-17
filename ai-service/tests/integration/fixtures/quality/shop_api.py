"""Shop API used by the output quality tests (Flask + FastAPI styles)."""
import functools

from fastapi import APIRouter
from flask import Flask
from pydantic import BaseModel

app = Flask(__name__)
router = APIRouter(prefix="/api/v1")


class Item(BaseModel):
    """An item in the shop."""
    name: str
    price: float = 0.0


class Store(dict):
    """In-memory store."""

    def add(self, item: Item) -> None:
        """Add an item.

        Args:
            item: The item to store.
        """
        self[item.name] = item


@app.route("/ping")
def ping():
    """Health check for load balancers."""
    return "ok"


@router.get("/items/{name}")
def get_item(name: str) -> Item:
    """Find one item by name.

    Args:
        name: Item name.

    Returns:
        The stored item.
    """
    return Item(name=name)


@router.post(path="/items")
def create_item(item: Item) -> Item:
    return item


@functools.lru_cache(maxsize=None)
def price_with_tax(price: float, rate: float = 0.1) -> float:
    """Price including tax."""
    return price * (1 + rate)

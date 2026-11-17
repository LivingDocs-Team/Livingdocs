"""Business rules for shopping carts."""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Cart:
    """A shopping cart: product id -> quantity."""
    items: Dict[int, int] = field(default_factory=dict)


class CartService:
    """Business rules for shopping carts. Prices are in VND and include VAT."""

    def __init__(self, prices: Dict[int, float]) -> None:
        self.prices = prices
        self.carts: Dict[int, Cart] = {}

    def add_item(self, cart_id: int, product_id: int, quantity: int = 1) -> Cart:
        """Add a product to the cart, creating the cart if needed."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        cart = self.carts.setdefault(cart_id, Cart())
        cart.items[product_id] = cart.items.get(product_id, 0) + quantity
        return cart

    def total(self, cart_id: int) -> float:
        """Total price of the cart including VAT."""
        cart = self.carts.get(cart_id, Cart())
        return sum(self.prices[p] * q for p, q in cart.items.items())

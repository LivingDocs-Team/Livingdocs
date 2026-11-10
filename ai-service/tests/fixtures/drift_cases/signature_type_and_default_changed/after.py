"""Shopping cart service."""
from fastapi import FastAPI, HTTPException

app = FastAPI()
DB = {}


@app.get("/carts/{cart_id}")
def get_total(cart_id: str, discount: float = 0.1) -> float:
    """Total of a cart in VND, VAT included."""
    cart = DB.get(cart_id)
    if cart is None:
        raise HTTPException(status_code=404, detail="cart not found")
    return sum(cart["items"]) - discount


def fetch_cart(cart_id: int, timeout: int = 30) -> dict:
    """Load a cart from the database."""
    return DB.get(cart_id, {"timeout": timeout})


def clear_cart(cart_id: int, timeout: int = 30) -> None:
    """Empty a cart."""
    DB.pop(cart_id, None)


def count_items(cart_id: int) -> int:
    """Number of items in a cart."""
    return len(DB.get(cart_id, {}).get("items", []))


def legacy_total(cart_id: int) -> float:
    """Old total kept for the mobile app."""
    return float(sum(DB.get(cart_id, {}).get("items", [])))

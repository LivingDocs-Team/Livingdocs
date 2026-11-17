from fastapi import FastAPI

from shop.cart_service import CartService

app = FastAPI()
service = CartService(prices={1: 10000.0, 2: 25000.0})


@app.get("/carts/{cart_id}/total")
def get_cart_total(cart_id: int) -> float:
    """Return the cart total in VND."""
    return service.total(cart_id)


@app.post("/carts/{cart_id}/items")
def add_cart_item(cart_id: int, product_id: int, quantity: int = 1) -> dict:
    cart = service.add_item(cart_id, product_id, quantity)
    return {"items": cart.items}

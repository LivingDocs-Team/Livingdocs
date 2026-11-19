"""Shared input for the drift detection tests (LD-150): one Python file before / after a
Pull Request, its diff, and documentation that describes the old code."""

PR = {"number": 42, "title": "LD-146 Cart: currency support", "head_branch": "ld-147-drift",
      "head_sha": "9f2c1e7", "url": "https://github.com/acme/shop/pull/42"}

# ---------- fixtures: one Python file before / after the Pull Request ----------

BEFORE = {
    "path": "shop/cart.py", "language": "python", "status": "ok",
    "functions": [
        {"name": "get_cart_total", "parameters": [{"name": "cart_id", "type": "int"},
                                                  {"name": "discount", "type": "float"}],
         "return_type": "float", "docstring": "Total of a cart.", "lineno": 10, "end_lineno": 14},
        {"name": "clear_cart", "parameters": [{"name": "cart_id", "type": "int"}],
         "lineno": 16, "end_lineno": 18},
        {"name": "_audit", "parameters": [{"name": "event", "type": "str"}],
         "lineno": 20, "end_lineno": 21},
        {"name": "count_items", "parameters": [{"name": "cart_id", "type": "int"}],
         "return_type": "int", "lineno": 23, "end_lineno": 25},
        {"name": "fetch_cart", "parameters": [{"name": "cart_id", "type": "int"}],
         "return_type": "Cart", "docstring": "Load a cart.", "lineno": 27, "end_lineno": 28},
    ],
    "endpoints": [
        {"http_method": "GET", "path": "/carts/{id}", "handler": "get_cart_total", "lineno": 9},
        {"http_method": "DELETE", "path": "/carts/{id}", "handler": "clear_cart", "lineno": 15},
    ],
    "classes": [{"name": "Cart", "lineno": 30, "end_lineno": 40,
                 "methods": [{"name": "add", "parameters": [{"name": "item"}],
                              "lineno": 31, "end_lineno": 33}]}],
}
AFTER = {
    "path": "shop/cart.py", "language": "python", "status": "ok",
    "functions": [
        {"name": "get_cart_total", "parameters": [{"name": "cart_id", "type": "int"},
                                                  {"name": "currency", "type": "str"}],
         "return_type": "float", "docstring": "Total of a cart.", "lineno": 10, "end_lineno": 15},
        {"name": "count_cart_items", "parameters": [{"name": "cart_id", "type": "int"}],
         "return_type": "int", "lineno": 23, "end_lineno": 25},
        {"name": "fetch_cart", "parameters": [{"name": "cart_id", "type": "int"}],
         "return_type": "Cart", "docstring": "Load a cart from the cache first.",
         "lineno": 27, "end_lineno": 28},
        {"name": "apply_coupon", "parameters": [{"name": "code", "type": "str"}],
         "lineno": 41, "end_lineno": 43},
    ],
    "endpoints": [
        {"http_method": "GET", "path": "/api/carts/{id}", "handler": "get_cart_total", "lineno": 9},
    ],
    "classes": [{"name": "Cart", "lineno": 30, "end_lineno": 40,
                 "methods": [{"name": "add", "parameters": [{"name": "item"}],
                              "lineno": 31, "end_lineno": 33}]}],
}
PATCH = """@@ -8,8 +8,9 @@ from shop.db import load

-@app.get("/carts/{id}")
-def get_cart_total(cart_id: int, discount: float) -> float:
+@app.get("/api/carts/{id}")
+def get_cart_total(cart_id: int, currency: str) -> float:
     cart = load(cart_id)
-    return sum(cart.items) - discount
+    total = sum(cart.items)
+    return convert(total, currency)
@@ -30,4 +31,4 @@ class Cart:
     def add(self, item):
-        self.items.append(item)
+        self.items.insert(0, item)
"""

# Markdown in the layout of the generated documentation (headings and code name the entities)
CART_SECTION = """# shop/cart.py

## Functions

### `get_cart_total`

```
get_cart_total(cart_id, discount)
```

| Name | Type |
|---|---|
| `cart_id` | int |
| `discount` | float |

### `clear_cart`

Empties the cart.

### `_audit`

Writes an audit event.

### `count_items`

Number of items.

### `fetch_cart`

Loads a cart.

## Classes

### `Cart`

#### `add`

Appends an item.

## API Endpoints

### `GET /carts/{id}`

### `DELETE /carts/{id}`
"""
USERS_SECTION = "# shop/users.py\n\n### `get_users`\n\nLists users. We add users here.\n"
README = {"path": "README.md", "content": (
    "# Shop\n\nRead a total with `GET /carts/:id`.\n"
    "Implementation: [cart](shop/cart.py), see `clear_cart()`.\n"
    "We add items to a cart.\n")}

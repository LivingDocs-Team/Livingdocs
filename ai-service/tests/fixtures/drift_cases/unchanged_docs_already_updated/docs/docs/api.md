# Cart API

## `get_total`

`GET /carts/{cart_id}` returns the total of a cart.

```
get_total(cart_id, currency="VND")
```

| Name | Type | Default |
|---|---|---|
| `cart_id` | int | - |
| `currency` | str | "VND" |

Total of a cart in VND, VAT included. Returns `404` when the cart does not exist.

## `fetch_cart`

`fetch_cart(cart_id, timeout=30)` loads a cart from the database.

## `clear_cart`

| Name | Type | Default |
|---|---|---|
| `cart_id` | int | - |
| `timeout` | int | 30 |

## `count_items`

`count_items(cart_id)` counts the items.

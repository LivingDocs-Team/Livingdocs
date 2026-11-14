"""Labelled benchmark for related-code and documentation retrieval (LD-336, LD-337).

A small online-shop repository: 14 analysed files (Python and Java) and 5 context documents
(English and Vietnamese). For every file we list, by hand, which code from OTHER files and
which documentation passages are really useful when writing its documentation.

The documents deliberately use other words than the code in some places, the way people
write: "basket" for cart, "promo code" for voucher, "value-added tax" for VAT, "sign in" for
login, "delivery cost" for shipping fee, and one guide is in Vietnamese. That is exactly where
keyword matching (TF-IDF) and meaning-based matching (embeddings) are expected to differ.

Labels are written by the author of the experiment, so the absolute numbers are only
indicative; the comparison between methods on the same labels is the point.
"""


def fn(name, params=(), ret=None, doc=None, src=None, sig=None):
    return {"name": name, "parameters": [{"name": p, "type": t} for p, t in params],
            "return_type": ret, "docstring": doc, "source": src, "signature": sig}


def cls(name, methods=(), doc=None, fields=(), bases=()):
    return {"name": name, "docstring": doc, "methods": list(methods), "bases": list(bases),
            "fields": [{"name": n, "type": t} for n, t in fields]}


def ep(method, path, handler, params=(), body=None, resp=None):
    return {"http_method": method, "path": path, "handler": handler,
            "parameters": [{"name": p, "type": t} for p, t in params],
            "request_body": body, "response": resp}


FILES = [
    {"path": "shop/cart/service.py", "language": "python", "classes": [cls(
        "CartService", doc="Business rules for a customer's cart.", methods=[
            fn("add_item", [("cart_id", "int"), ("product_id", "int"), ("quantity", "int")], "Cart",
               src="def add_item(self, cart_id, product_id, quantity):\n    StockService().reserve(product_id, quantity)\n    ..."),
            fn("remove_item", [("cart_id", "int"), ("product_id", "int")], "Cart"),
            fn("total", [("cart_id", "int")], "float",
               src="def total(self, cart_id):\n    subtotal = sum(i.price * i.quantity for i in cart.items)\n    return compute_vat(subtotal)"),
            fn("apply_voucher", [("cart_id", "int"), ("code", "str")], "float",
               src="def apply_voucher(self, cart_id, code):\n    VoucherValidator().validate(code)\n    ..."),
        ])]},
    {"path": "shop/cart/routes.py", "language": "python",
     "functions": [
         fn("add_to_cart", [("cart_id", "int"), ("item", "CartItem")], "Cart",
            src="def add_to_cart(cart_id, item):\n    return CartService().add_item(cart_id, item.product_id, item.quantity)"),
         fn("get_cart_total", [("cart_id", "int")], "float",
            src="def get_cart_total(cart_id):\n    return CartService().total(cart_id)"),
         fn("redeem_voucher", [("cart_id", "int"), ("code", "str")], "float",
            src="def redeem_voucher(cart_id, code):\n    return CartService().apply_voucher(cart_id, code)")],
     "endpoints": [ep("POST", "/carts/{cart_id}/items", "add_to_cart", [("cart_id", "int")], "CartItem", "Cart"),
                   ep("GET", "/carts/{cart_id}/total", "get_cart_total", [("cart_id", "int")], resp="float"),
                   ep("POST", "/carts/{cart_id}/voucher", "redeem_voucher", [("cart_id", "int")], "VoucherCode", "float")]},
    {"path": "shop/cart/models.py", "language": "python", "classes": [
        cls("Cart", doc="Products a customer intends to buy.", fields=[("id", "int"), ("items", "list[CartItem]"), ("owner_id", "int")]),
        cls("CartItem", fields=[("product_id", "int"), ("quantity", "int"), ("price", "float")])]},
    {"path": "shop/pricing/tax.py", "language": "python", "functions": [
        fn("compute_vat", [("amount", "float"), ("rate", "float")], "float", doc="Add VAT to a net amount."),
        fn("vat_rate_for", [("category", "str")], "float")]},
    {"path": "shop/pricing/voucher.py", "language": "python", "classes": [cls(
        "VoucherValidator", doc="Checks voucher codes.", methods=[
            fn("validate", [("code", "str")], "Voucher"),
            fn("is_expired", [("voucher", "Voucher")], "bool"),
            fn("discount_percent", [("voucher", "Voucher")], "int")])]},
    {"path": "shop/orders/service.py", "language": "python", "classes": [cls(
        "OrderService", doc="Turns a cart into an order and manages its life cycle.", methods=[
            fn("place_order", [("cart_id", "int"), ("card_token", "str")], "Order",
               src="def place_order(self, cart_id, card_token):\n    total = CartService().total(cart_id)\n    PaymentGateway().charge(card_token, total)\n    EmailSender().sendOrderConfirmation(order)"),
            fn("cancel_order", [("order_id", "int")], "Order",
               src="def cancel_order(self, order_id):\n    PaymentGateway().refund_payment(order.payment_id)\n    StockService().release(order)"),
        ])]},
    {"path": "shop/orders/routes.py", "language": "python",
     "functions": [fn("create_order", [("body", "OrderRequest")], "Order",
                      src="def create_order(body):\n    return OrderService().place_order(body.cart_id, body.card_token)"),
                   fn("delete_order", [("order_id", "int")], "Order",
                      src="def delete_order(order_id):\n    return OrderService().cancel_order(order_id)")],
     "endpoints": [ep("POST", "/orders", "create_order", body="OrderRequest", resp="Order"),
                   ep("DELETE", "/orders/{order_id}", "delete_order", [("order_id", "int")], resp="Order")]},
    {"path": "shop/payments/gateway.py", "language": "python", "classes": [cls(
        "PaymentGateway", doc="Client for the card payment provider.", methods=[
            fn("charge", [("card_token", "str"), ("amount", "float")], "Payment"),
            fn("refund_payment", [("payment_id", "str")], "Refund")])]},
    {"path": "shop/users/auth.py", "language": "python", "functions": [
        fn("login", [("email", "str"), ("password", "str")], "Token",
           src="def login(email, password):\n    user = find_user(email)\n    if not verify_password(password, user.password_hash): raise AuthError\n    return issue_token(user)"),
        fn("hash_password", [("raw", "str")], "str"),
        fn("verify_password", [("raw", "str"), ("hashed", "str")], "bool"),
        fn("issue_token", [("user", "User")], "Token", doc="Create a signed JWT for the user.")]},
    {"path": "shop/users/routes.py", "language": "python",
     "functions": [fn("post_login", [("body", "LoginRequest")], "Token",
                      src="def post_login(body):\n    return login(body.email, body.password)"),
                   fn("post_register", [("body", "RegisterRequest")], "User",
                      src="def post_register(body):\n    return create_user(body.email, hash_password(body.password))")],
     "endpoints": [ep("POST", "/auth/login", "post_login", body="LoginRequest", resp="Token"),
                   ep("POST", "/auth/register", "post_register", body="RegisterRequest", resp="User")]},
    {"path": "shop/inventory/stock.py", "language": "python", "classes": [cls(
        "StockService", doc="Warehouse quantities per product.", methods=[
            fn("reserve", [("product_id", "int"), ("quantity", "int")], "None"),
            fn("release", [("order", "Order")], "None"),
            fn("available_quantity", [("product_id", "int")], "int")])]},
    {"path": "src/main/java/com/shop/notify/EmailSender.java", "language": "java", "classes": [cls(
        "EmailSender", doc="Sends transactional e-mails.", methods=[
            fn("sendOrderConfirmation", [("order", "Order")], "void"),
            fn("sendPasswordReset", [("user", "User"), ("link", "String")], "void")])]},
    {"path": "shop/reports/sales.py", "language": "python", "functions": [
        fn("daily_revenue", [("day", "date")], "float", doc="Sum of paid orders for one day."),
        fn("top_products", [("limit", "int")], "list[Product]")]},
    {"path": "shop/shipping/fee.py", "language": "python", "functions": [
        fn("shipping_fee", [("weight_kg", "float"), ("distance_km", "float")], "float")]},
]

DOCS = [
    {"path": "README.md", "title": "Shop", "content": """# Shop

Online shop backend.

## Basket

Customers put products in their basket. The basket shows the amount to pay, tax included.

## Checkout

Checking out turns the basket into an order and charges the customer's card. A confirmation
is sent by e-mail.

## Promo codes

A promo code gives a percentage off. Codes past their end date are rejected.

## Installation

```bash
# create a virtual environment
python -m venv venv
pip install -r requirements.txt
```

## Deployment

Build the image and run docker compose up.
"""},
    {"path": "docs/pricing.md", "title": "Pricing", "content": """# Pricing

## Value-added tax

Prices are shown with value-added tax. The standard rate is 10%, books use 5%.

## Delivery cost

The delivery cost depends on parcel weight and the distance to the customer.
"""},
    {"path": "docs/security.md", "title": "Security", "content": """# Security

## Passwords

Passwords are never stored in clear text; only a bcrypt hash is kept.

## Sessions

After a user signs in, the server returns a signed JSON Web Token used on every request.
"""},
    {"path": "docs/vi/huong-dan.md", "title": "Hướng dẫn", "content": """# Hướng dẫn sử dụng

## Giỏ hàng

Khách thêm sản phẩm vào giỏ hàng; hệ thống tự tính tổng tiền đã gồm thuế.

## Hủy đơn và hoàn tiền

Khi khách hủy đơn hàng, tiền được hoàn lại qua cổng thanh toán và hàng được trả về kho.

## Báo cáo doanh thu

Báo cáo doanh thu theo ngày và danh sách sản phẩm bán chạy.
"""},
    {"path": "docs/operations.md", "title": "Operations", "content": """# Operations

## Warehouse

Items are held in the warehouse when an order is placed and put back when it is cancelled.

## Notifications

Customers receive an e-mail when their order is confirmed or when they ask to reset a password.
"""},
]

# Relevant results for each file: code from other files ("path::name") and documentation
# passages ("path::section heading").
GOLD = {
    "shop/cart/service.py": {
        "code": ["shop/cart/routes.py::POST /carts/{cart_id}/items", "shop/cart/routes.py::GET /carts/{cart_id}/total",
                 "shop/cart/routes.py::POST /carts/{cart_id}/voucher", "shop/cart/models.py::Cart",
                 "shop/cart/models.py::CartItem", "shop/pricing/tax.py::compute_vat",
                 "shop/pricing/voucher.py::VoucherValidator.validate", "shop/inventory/stock.py::StockService.reserve",
                 "shop/cart/routes.py::get_cart_total", "shop/cart/routes.py::add_to_cart",
                 "shop/cart/routes.py::redeem_voucher"],
        "docs": ["README.md::Basket", "README.md::Promo codes", "docs/vi/huong-dan.md::Giỏ hàng"]},
    "shop/cart/routes.py": {
        "code": ["shop/cart/service.py::CartService", "shop/cart/service.py::CartService.add_item",
                 "shop/cart/service.py::CartService.total", "shop/cart/service.py::CartService.apply_voucher",
                 "shop/cart/models.py::Cart", "shop/cart/models.py::CartItem"],
        "docs": ["README.md::Basket", "README.md::Promo codes", "docs/vi/huong-dan.md::Giỏ hàng"]},
    "shop/cart/models.py": {
        "code": ["shop/cart/service.py::CartService", "shop/cart/routes.py::add_to_cart",
                 "shop/cart/routes.py::POST /carts/{cart_id}/items", "shop/cart/service.py::CartService.add_item"],
        "docs": ["README.md::Basket", "docs/vi/huong-dan.md::Giỏ hàng"]},
    "shop/pricing/tax.py": {
        "code": ["shop/cart/service.py::CartService.total"],
        "docs": ["docs/pricing.md::Value-added tax"]},
    "shop/pricing/voucher.py": {
        "code": ["shop/cart/service.py::CartService.apply_voucher", "shop/cart/routes.py::redeem_voucher",
                 "shop/cart/routes.py::POST /carts/{cart_id}/voucher"],
        "docs": ["README.md::Promo codes"]},
    "shop/orders/service.py": {
        "code": ["shop/cart/service.py::CartService.total", "shop/payments/gateway.py::PaymentGateway.charge",
                 "shop/payments/gateway.py::PaymentGateway.refund_payment", "shop/orders/routes.py::create_order",
                 "shop/orders/routes.py::delete_order", "shop/orders/routes.py::POST /orders",
                 "shop/orders/routes.py::DELETE /orders/{order_id}", "shop/inventory/stock.py::StockService.release",
                 "src/main/java/com/shop/notify/EmailSender.java::EmailSender.sendOrderConfirmation"],
        "docs": ["README.md::Checkout", "docs/vi/huong-dan.md::Hủy đơn và hoàn tiền", "docs/operations.md::Warehouse",
                 "docs/operations.md::Notifications"]},
    "shop/orders/routes.py": {
        "code": ["shop/orders/service.py::OrderService", "shop/orders/service.py::OrderService.place_order",
                 "shop/orders/service.py::OrderService.cancel_order"],
        "docs": ["README.md::Checkout", "docs/vi/huong-dan.md::Hủy đơn và hoàn tiền"]},
    "shop/payments/gateway.py": {
        "code": ["shop/orders/service.py::OrderService.place_order", "shop/orders/service.py::OrderService.cancel_order"],
        "docs": ["README.md::Checkout", "docs/vi/huong-dan.md::Hủy đơn và hoàn tiền"]},
    "shop/users/auth.py": {
        "code": ["shop/users/routes.py::post_login", "shop/users/routes.py::post_register",
                 "shop/users/routes.py::POST /auth/login", "shop/users/routes.py::POST /auth/register"],
        "docs": ["docs/security.md::Passwords", "docs/security.md::Sessions"]},
    "shop/users/routes.py": {
        "code": ["shop/users/auth.py::login", "shop/users/auth.py::hash_password", "shop/users/auth.py::issue_token"],
        "docs": ["docs/security.md::Passwords", "docs/security.md::Sessions"]},
    "shop/inventory/stock.py": {
        "code": ["shop/cart/service.py::CartService.add_item", "shop/orders/service.py::OrderService.cancel_order"],
        "docs": ["docs/operations.md::Warehouse"]},
    "src/main/java/com/shop/notify/EmailSender.java": {
        "code": ["shop/orders/service.py::OrderService.place_order"],
        "docs": ["docs/operations.md::Notifications", "README.md::Checkout"]},
    "shop/reports/sales.py": {
        "code": [],
        "docs": ["docs/vi/huong-dan.md::Báo cáo doanh thu"]},
    "shop/shipping/fee.py": {
        "code": [],
        "docs": ["docs/pricing.md::Delivery cost"]},
}


def request():
    return {"scope": "repository", "target": "shop", "files": FILES, "context": DOCS}

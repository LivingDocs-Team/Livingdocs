from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://localhost:3000/#/login", wait_until="networkidle")
    page.wait_for_timeout(2000)

    print("=== URL ===", page.url)
    print("=== INPUTS ===")
    for el in page.query_selector_all("input"):
        print({
            "type": el.get_attribute("type"),
            "id": el.get_attribute("id"),
            "name": el.get_attribute("name"),
            "placeholder": el.get_attribute("placeholder"),
            "aria-label": el.get_attribute("aria-label"),
        })
    print("=== LABELS ===")
    for el in page.query_selector_all("label"):
        print({"for": el.get_attribute("for"), "text": el.inner_text().strip()})
    print("=== BUTTONS ===")
    for el in page.query_selector_all("button"):
        print(repr(el.inner_text().strip()))
    print("=== BODY TEXT ===")
    print(page.inner_text("body")[:500])

    browser.close()

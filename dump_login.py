from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://localhost:3000/")
    page.wait_for_timeout(3000)
    html = page.content()
    with open("login_dump.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved login_dump.html, length:", len(html))
    browser.close()
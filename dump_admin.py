from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # Bắt các request và response
    def log_request(request):
        if "/api/" in request.url:
            print(f"REQ: {request.method} {request.url}")
            
    def log_response(response):
        if "/api/" in response.url:
            print(f"RES: {response.status} {response.url}")
            try:
                # Cố gắng in body của response
                print(f"BODY: {response.text()[:200]}")
            except:
                pass

    page.on("request", log_request)
    page.on("response", log_response)

    page.goto("http://127.0.0.1:3000/#/login")
    page.get_by_label("Email").fill("admin@example.test")
    page.get_by_label("Password").fill("Password123!")
    
    print("--- BẤM ĐĂNG NHẬP ---")
    page.get_by_role("button", name="Sign in").click()
    
    page.wait_for_timeout(3000)
    print("--- URL HIỆN TẠI:", page.url)
    browser.close()
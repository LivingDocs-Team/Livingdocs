"""LD-52: kiểm thử màn hình hồ sơ (LD-49, LD-50) và tùy chọn thông báo (LD-51) của LD-48.

Test chạy trên giao diện thật trong trình duyệt (Playwright). Mọi request /api/** được giả lập,
nên chỉ cần frontend chạy ở FRONTEND_URL (mặc định http://localhost:3000), không cần backend.

Chạy trên máy:
    cd frontend && npm ci && npm run build && npx vite preview --port 3000
    python -m pytest -o addopts="" -v tests/test_profile_preferences.py
"""
import json
import os
import urllib.request

import pytest

pytest.importorskip("pytest_playwright", reason="cần cài pytest-playwright để chạy test giao diện")

from playwright.sync_api import Page, expect  # noqa: E402

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
USER_ID = "48"


@pytest.fixture(scope="module", autouse=True)
def frontend_is_running():
    """Bỏ qua cả file nếu frontend chưa chạy; trong CI (FRONTEND_E2E_REQUIRED=true) thì báo lỗi."""
    try:
        urllib.request.urlopen(FRONTEND_URL, timeout=5).close()
    except OSError as error:
        message = f"Frontend chưa chạy ở {FRONTEND_URL}: {error}"
        if os.environ.get("FRONTEND_E2E_REQUIRED") == "true":
            pytest.fail(message)
        pytest.skip(message)


class FakeBackend:
    """Backend giả: hồ sơ và tùy chọn thông báo của người dùng đang đăng nhập."""

    def __init__(self):
        self.profile = {"id": 48, "username": "dang", "email": "dang@example.test",
                        "firstName": "Hai", "lastName": "Dang", "role": "DEVELOPER"}
        self.preferences = {"emailUpdates": True, "documentChanges": True,
                            "reviewRequests": False, "systemNotifications": True}
        self.writes = []   # (method, path, body, CSRF header)

    def handle(self, route):
        request = route.request
        path = request.url.split("?", 1)[0].removeprefix(FRONTEND_URL)
        if request.method in ("PATCH", "PUT"):
            self.writes.append((request.method, path, json.loads(request.post_data or "{}"),
                                request.headers.get("x-xsrf-token")))

        if (request.method, path) == ("GET", "/api/auth/csrf"):
            return route.fulfill(status=200, json={"token": "csrf-ld48"})
        if (request.method, path) == ("GET", "/api/auth/me"):
            return route.fulfill(status=200, json={"id": USER_ID, "email": self.profile["email"]})
        if (request.method, path) == ("GET", "/api/profile"):
            return route.fulfill(status=200, json=self.profile)
        if (request.method, path) == ("PATCH", "/api/profile"):
            body = self.writes[-1][2]
            if body.get("username") == "taken":
                return route.fulfill(status=409, json={"status": 409, "code": "USERNAME_TAKEN",
                                                       "message": "Username is already in use."})
            self.profile.update({k: body[k].strip() for k in ("username", "firstName", "lastName") if k in body})
            return route.fulfill(status=200, json=self.profile)
        if (request.method, path) == ("GET", "/api/profile/notification-preferences"):
            return route.fulfill(status=200, json=self.preferences)
        if (request.method, path) == ("PUT", "/api/profile/notification-preferences"):
            self.preferences = self.writes[-1][2]
            return route.fulfill(status=200, json=self.preferences)
        return route.fulfill(status=404, json={"message": f"Unexpected API request: {request.method} {path}"})


def open_page(page: Page, backend: FakeBackend, button: str) -> None:
    page.add_init_script(f"window.sessionStorage.setItem('livingdocs.userId', '{USER_ID}')")
    page.route("**/api/**", backend.handle)
    page.goto(FRONTEND_URL + "/")
    page.get_by_role("button", name=button, exact=True).click()  # menu of the signed-in app


def test_profile_is_loaded_and_saved(page: Page):
    backend = FakeBackend()
    open_page(page, backend, "Profile")

    expect(page.get_by_role("heading", name="User Profile")).to_be_visible()
    expect(page.get_by_label("Username")).to_have_value("dang")
    expect(page.get_by_label("Email")).to_have_value("dang@example.test")
    expect(page.get_by_label("Email")).not_to_be_editable()

    page.get_by_label("First name").fill("Le Hien Hai")
    page.get_by_label("Username").fill("dang-le")
    page.get_by_role("button", name="Save changes").click()

    expect(page.get_by_role("status")).to_have_text("Profile saved.")
    assert backend.writes == [("PATCH", "/api/profile",
                               {"username": "dang-le", "firstName": "Le Hien Hai", "lastName": "Dang"}, "csrf-ld48")]
    expect(page.get_by_label("First name")).to_have_value("Le Hien Hai")


def test_taken_username_shows_the_error(page: Page):
    open_page(page, FakeBackend(), "Profile")

    page.get_by_label("Username").fill("taken")
    page.get_by_role("button", name="Save changes").click()

    expect(page.get_by_role("alert")).to_have_text("Username is already in use.")


def test_notification_preferences_are_loaded_and_saved(page: Page):
    backend = FakeBackend()
    open_page(page, backend, "Notifications")

    expect(page.get_by_role("heading", name="Notification Preferences")).to_be_visible()
    expect(page.get_by_label("Review requests")).not_to_be_checked()
    expect(page.get_by_label("Email updates")).to_be_checked()

    page.get_by_label("Review requests").check()
    page.get_by_label("Email updates").uncheck()
    page.get_by_role("button", name="Save preferences").click()

    expect(page.get_by_role("status")).to_have_text("Preferences saved.")
    assert backend.writes == [("PUT", "/api/profile/notification-preferences",
                               {"emailUpdates": False, "documentChanges": True,
                                "reviewRequests": True, "systemNotifications": True}, "csrf-ld48")]

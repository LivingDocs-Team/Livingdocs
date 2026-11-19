"""Navigation helpers for the role-based app shell (frontend/src/rbac).

After sign-in every role sees a sidebar ("Main menu") built from its screen flow; screens are opened
from that menu or directly by hash URL (http://localhost:3000/#/review/queue).
"""
import os

from playwright.sync_api import Page

# Same source as the other browser tests (FRONTEND_URL overrides the default).
FRONTEND = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
LOGIN_URL = f"{FRONTEND}/#/login"


def main_menu(page: Page):
    return page.get_by_role("navigation", name="Main menu")


def menu_link(page: Page, label: str):
    return main_menu(page).get_by_role("link", name=label, exact=True)


def open_screen(page: Page, label: str):
    """Click a screen of the signed-in role's menu, e.g. open_screen(page, "Review Queue")."""
    menu_link(page, label).click()


def open_tile(page: Page, label: str):
    """Open a box on a "choose a section" page (Profile & Settings), e.g. open_tile(page, "Profile")."""
    page.locator(".tile", has_text=label).click()


def sign_in(page: Page, email: str = "user@example.test", password: str = "test-only-password"):
    """Fill and submit the Login form (the page must already show it)."""
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in").click()

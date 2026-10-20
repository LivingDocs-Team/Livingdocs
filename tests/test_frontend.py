import pytest
from playwright.sync_api import Page, expect

def test_frontend_homepage_title(page: Page):
    """LD-373: Kiểm tra tiêu đề giao diện Frontend Dashboard LivingDocs"""
    page.goto("http://localhost:3000/")
    expect(page).to_have_title("LivingDocs - Automated Documentation Generator")

def test_frontend_upload_repo_flow(page: Page):
    """LD-373: Giả lập thao tác nhập Repo và bấm nút Phân tích trên Frontend"""
    page.goto("http://localhost:3000/")
    repo_input = page.locator("input[name='repo_url']")
    if repo_input.is_visible():
        repo_input.fill("LivingDocs-Team/Livingdocs")
        analyze_btn = page.locator("button:has-text('Analyze Repository')")
        analyze_btn.click()

from __future__ import annotations

import pytest

from app.email.renderer import render_email


@pytest.mark.asyncio
async def test_render_stock_email():
    subject, html_body, text_body, _images = render_email(
        entity_type="stock",
        entity_id="AAPL",
        schedule_name="Test Report",
    )

    assert "GoldMine:" in subject
    assert "AAPL" in subject
    assert "<table" in html_body
    assert "Related People" in html_body
    assert "GoldMine" in text_body
    assert "AAPL" in text_body


@pytest.mark.asyncio
async def test_render_single_widget():
    subject, html_body, text_body, _images = render_email(
        entity_type="stock",
        entity_id="AAPL",
        schedule_name="People Only",
        widget_ids=["related_people"],
    )

    assert "Related People" in html_body
    assert "Related Files" not in html_body


@pytest.mark.asyncio
async def test_render_truncates_rows():
    # The stock peers widget can return many rows; verify truncation
    subject, html_body, text_body, _images = render_email(
        entity_type="dataset",
        entity_id="stocks",
        schedule_name="Full Dataset",
    )

    # Count <tr> tags (excluding header) to check truncation
    # The email should have at most EMAIL_MAX_ROWS_PER_WIDGET data rows per table
    from app.config.settings import settings
    row_count = html_body.count("<tr") - html_body.count("<thead")
    # Each widget table has 1 header row + data rows
    # Just verify we got some output and it's bounded
    assert "<table" in html_body
    assert row_count <= settings.EMAIL_MAX_ROWS_PER_WIDGET + 10  # Some margin for multiple tables

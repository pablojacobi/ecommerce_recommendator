"""Tests for Django template rendering - ensures no broken template tags."""

import pytest
from django.template.loader import get_template, render_to_string
from django.template import TemplateSyntaxError


class TestTemplateCompilation:
    """Test that all templates compile without syntax errors."""

    CHAT_TEMPLATES = [
        "chat/index.html",
        "chat/partials/assistant_message.html",
        "chat/partials/assistant_message_stored.html",
        "chat/partials/user_message.html",
        "chat/partials/typing_indicator.html",
    ]

    @pytest.mark.parametrize("template_name", CHAT_TEMPLATES)
    def test_template_compiles(self, template_name: str) -> None:
        """Each template should compile without TemplateSyntaxError."""
        try:
            get_template(template_name)
        except TemplateSyntaxError as e:
            pytest.fail(f"Template {template_name} has syntax error: {e}")


class TestAssistantMessageRendering:
    """Test that assistant_message templates render correctly with data."""

    SAMPLE_PRODUCTS = [
        {
            "id": "123",
            "title": "Test Gaming Laptop RTX 4070",
            "price": 1299.99,
            "currency": "USD",
            "url": "https://example.com/product/123",
            "image_url": "https://example.com/img.jpg",
            "marketplace_code": "EBAY_US",
            "marketplace_name": "eBay United States",
            "seller_rating": 4.8,
            "shipping_cost": 25.00,
            "free_shipping": False,
            "is_best_price": True,
            "tax_info": {
                "product_price_usd": 1299.99,
                "shipping_cost_usd": 25.00,
                "customs_duty": 77.99,
                "vat": 266.58,
                "total_taxes": 344.57,
                "total_with_taxes": 1669.56,
                "de_minimis_applied": False,
            },
        },
        {
            "id": "456",
            "title": "Another Product",
            "price": 599.00,
            "currency": "USD",
            "url": "https://example.com/product/456",
            "image_url": None,
            "marketplace_code": "MLC",
            "marketplace_name": "MercadoLibre Chile",
            "seller_rating": None,
            "shipping_cost": None,
            "free_shipping": True,
            "is_best_price": False,
            "tax_info": None,
        },
    ]

    def test_assistant_message_renders_products(self) -> None:
        """assistant_message.html should render products without raw template tags."""
        html = render_to_string(
            "chat/partials/assistant_message.html",
            {
                "message": "Found 2 products for your search.",
                "products": self.SAMPLE_PRODUCTS,
                "has_more": True,
                "conversation_id": "test-uuid-123",
            },
        )

        # Should contain rendered values, not raw template tags
        assert "{{ product" not in html, "Raw template tags found in output"
        assert "{% if" not in html, "Raw template tags found in output"
        assert "{% for" not in html, "Raw template tags found in output"
        assert "{% endif" not in html, "Raw template tags found in output"
        assert "{% endfor" not in html, "Raw template tags found in output"

        # Should contain actual values
        assert "Test Gaming Laptop RTX 4070" in html
        assert "USD 1300" in html or "USD 1,300" in html or "USD 1299" in html
        assert "eBay United States" in html
        assert "Best Price" in html
        assert "Total landed" in html
        assert "1669" in html  # total_with_taxes
        assert "Another Product" in html
        assert "Free shipping" in html

    def test_assistant_message_stored_renders_products(self) -> None:
        """assistant_message_stored.html should render products without raw template tags."""
        html = render_to_string(
            "chat/partials/assistant_message_stored.html",
            {
                "message": "Found products from history.",
                "products": self.SAMPLE_PRODUCTS,
                "has_more": False,
                "conversation_id": "test-uuid-456",
            },
        )

        # Should contain rendered values, not raw template tags
        assert "{{ product" not in html, "Raw template tags found in output"
        assert "{% if" not in html, "Raw template tags found in output"
        assert "{% for" not in html, "Raw template tags found in output"

        # Should contain actual values
        assert "Test Gaming Laptop RTX 4070" in html
        assert "USD" in html
        assert "eBay United States" in html

    def test_assistant_message_without_products(self) -> None:
        """assistant_message.html should render correctly without products."""
        html = render_to_string(
            "chat/partials/assistant_message.html",
            {
                "message": "No products found matching your search.",
                "products": [],
                "has_more": False,
            },
        )

        assert "{{ " not in html, "Raw template tags found in output"
        assert "{% " not in html, "Raw template tags found in output"
        assert "No products found" in html

    def test_assistant_message_with_none_products(self) -> None:
        """assistant_message.html should handle None products gracefully."""
        html = render_to_string(
            "chat/partials/assistant_message.html",
            {
                "message": "Error occurred.",
                "products": None,
                "has_more": False,
            },
        )

        assert "{{ " not in html, "Raw template tags found in output"
        assert "Error occurred" in html


class TestUserMessageRendering:
    """Test user_message template rendering."""

    def test_user_message_renders(self) -> None:
        """user_message.html should render without raw template tags."""
        html = render_to_string(
            "chat/partials/user_message.html",
            {"message": "Find me a gaming laptop"},
        )

        assert "{{ " not in html, "Raw template tags found in output"
        assert "Find me a gaming laptop" in html


class TestNoSplitTemplateTags:
    """Ensure template files don't have split Django tags across lines."""

    TEMPLATE_FILES = [
        "templates/chat/partials/assistant_message.html",
        "templates/chat/partials/assistant_message_stored.html",
        "templates/chat/index.html",
    ]

    @pytest.mark.parametrize("template_path", TEMPLATE_FILES)
    def test_no_split_variable_tags(self, template_path: str) -> None:
        """Variable tags {{ }} should not be split across lines."""
        import os
        from pathlib import Path

        # Get the project root
        project_root = Path(__file__).parent.parent
        full_path = project_root / template_path

        if not full_path.exists():
            pytest.skip(f"Template {template_path} not found")

        content = full_path.read_text()
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            # Check for opening {{ without closing }} on same line
            if "{{" in line and "}}" not in line:
                # Check if it's a complete tag that just happens to have }} on next line
                open_count = line.count("{{")
                close_count = line.count("}}")
                if open_count > close_count:
                    pytest.fail(
                        f"{template_path}:{i} - Split variable tag detected: {line.strip()}"
                    )

    @pytest.mark.parametrize("template_path", TEMPLATE_FILES)
    def test_no_split_block_tags(self, template_path: str) -> None:
        """Block tags {% %} should not be split across lines."""
        import os
        from pathlib import Path

        project_root = Path(__file__).parent.parent
        full_path = project_root / template_path

        if not full_path.exists():
            pytest.skip(f"Template {template_path} not found")

        content = full_path.read_text()
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            # Check for opening {% without closing %} on same line
            if "{%" in line and "%}" not in line:
                open_count = line.count("{%")
                close_count = line.count("%}")
                if open_count > close_count:
                    pytest.fail(
                        f"{template_path}:{i} - Split block tag detected: {line.strip()}"
                    )

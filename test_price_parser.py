from app.providers.generic_price_page import extract_prices_from_text


def test_extract_brl_prices():
    text = "Ida R$ 399,90 volta R$ 1.234,56 taxa R$ 19,00"
    assert extract_prices_from_text(text) == [399.90, 1234.56]

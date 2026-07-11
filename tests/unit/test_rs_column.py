"""Unit test for RS Rating column configuration"""

def test_rs_rating_column_present():
    """Ensure RS Rating column is defined in the JS column config."""
    import pathlib
    js_path = pathlib.Path('static/js/app.js')
    content = js_path.read_text(encoding='utf-8')
    assert "id: 'relative_strength_rating'" in content, "RS column id missing"
    assert "name: 'RS Rating'" in content, "RS column name missing"

    # Verify rendering usage for RS Rating column
    assert "renderFundVal(stock.relative_strength_rating, 0)" in content, "RS rendering missing or incorrect"
    assert "%" not in content.split("relative_strength_rating")[1].split("renderFundVal")[0], "RS column should not include percent sign"
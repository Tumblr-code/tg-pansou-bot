from keyboards import create_all_results_keyboard, create_pagination_keyboard


def test_all_results_preserves_search_navigation_without_external_links():
    markup = create_all_results_keyboard("1:2:3")
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert [button.callback_data for button in buttons] == ["back:1:2:3", "refresh:1:2:3"]
    assert all(button.url is None for button in buttons)


def test_pagination_preserves_owner_key_and_page_navigation():
    markup = create_pagination_keyboard("1:2:3", "quark", 2, 3)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "type:1:2:3:quark:1" in callbacks
    assert "type:1:2:3:quark:3" in callbacks
    assert "back:1:2:3" in callbacks

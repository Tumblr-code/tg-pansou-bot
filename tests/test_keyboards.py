from keyboards import AD_LINKS, create_ad_button_rows


def test_ad_links_use_nexastore_destinations() -> None:
    assert AD_LINKS == (
        ("🤖 店铺助手", "https://t.me/NexaStoreRobot"),
        ("📢 频道", "https://t.me/NexaStoreChannel"),
        ("💬 群组", "https://t.me/NexaStoreGroup"),
    )

    rows = create_ad_button_rows()
    assert [(button.text, button.url) for row in rows for button in row] == list(AD_LINKS)

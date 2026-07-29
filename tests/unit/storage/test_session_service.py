from __future__ import annotations


def test_session_preview_prefers_summary(storage):
    service = storage["service"]
    record = service.create("user_a", "window_1")
    storage["message_repo"].add_user_message("user_a", record.id, "第一条消息")
    service.touch_and_set_title_if_empty("user_a", record.id, "标题内容")
    storage["summary_repo"].upsert("user_a", record.id, "压缩摘要优先", 1)

    assert service.list_sessions("user_a")[0].preview == "压缩摘要优先"


def test_session_preview_falls_back_to_title(storage):
    service = storage["service"]
    record = service.create("user_a", "window_1")
    service.touch_and_set_title_if_empty("user_a", record.id, "标题内容")

    assert service.list_sessions("user_a")[0].preview == "标题内容"


def test_session_preview_falls_back_to_first_message(storage):
    service = storage["service"]
    record = service.create("user_a", "window_1")
    storage["message_repo"].add_user_message("user_a", record.id, "第一条消息")

    assert service.list_sessions("user_a")[0].preview == "第一条消息"


def test_identifiers_are_normalized_and_limited(storage):
    service = storage["service"]
    record = service.create(" 用户 A ", "../window\\one")

    assert record.user_id == "用户-A"
    assert record.id == "window-one"
    assert len(service.normalize_session_id("x" * 200)) == 100


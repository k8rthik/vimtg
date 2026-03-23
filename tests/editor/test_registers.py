"""Tests for vimtg.editor.registers — vim-style register storage."""

from vimtg.editor.registers import Register, RegisterStore


class TestRegisterDefaults:
    def test_unnamed_default_empty(self) -> None:
        store = RegisterStore()
        assert store.unnamed == Register(content=())

    def test_get_unknown_returns_empty(self) -> None:
        store = RegisterStore()
        reg = store.get("x")
        assert reg.content == ()
        assert reg.linewise is True


class TestSetAndGet:
    def test_set_and_get_named(self) -> None:
        store = RegisterStore()
        updated = store.set("a", ("line1", "line2"))
        assert updated.get("a").content == ("line1", "line2")

    def test_set_preserves_linewise_flag(self) -> None:
        store = RegisterStore()
        updated = store.set("a", ("text",), linewise=False)
        assert updated.get("a").linewise is False

    def test_set_does_not_mutate_original(self) -> None:
        store = RegisterStore()
        _ = store.set("a", ("line1",))
        assert store.get("a").content == ()

    def test_set_overwrites_existing(self) -> None:
        store = RegisterStore()
        s1 = store.set("a", ("old",))
        s2 = s1.set("a", ("new",))
        assert s2.get("a").content == ("new",)


class TestUppercaseAppends:
    def test_uppercase_appends_to_lowercase(self) -> None:
        store = RegisterStore()
        s1 = store.set("a", ("line1",))
        s2 = s1.set("A", ("line2",))
        assert s2.get("a").content == ("line1", "line2")

    def test_uppercase_creates_if_lowercase_empty(self) -> None:
        store = RegisterStore()
        updated = store.set("B", ("first",))
        assert updated.get("b").content == ("first",)


class TestSetUnnamedYank:
    def test_set_unnamed_yank_stores_in_quote_and_zero(self) -> None:
        store = RegisterStore()
        updated = store.set_unnamed(("yanked line",), is_delete=False)
        assert updated.get('"').content == ("yanked line",)
        assert updated.get("0").content == ("yanked line",)

    def test_set_unnamed_yank_does_not_touch_numbered(self) -> None:
        store = RegisterStore()
        updated = store.set_unnamed(("text",), is_delete=False)
        assert updated.get("1").content == ()


class TestSetUnnamedDelete:
    def test_set_unnamed_delete_stores_in_quote_and_one(self) -> None:
        store = RegisterStore()
        updated = store.set_unnamed(("deleted line",), is_delete=True)
        assert updated.get('"').content == ("deleted line",)
        assert updated.get("1").content == ("deleted line",)

    def test_set_unnamed_delete_shifts_numbered_registers(self) -> None:
        store = RegisterStore()
        s1 = store.set_unnamed(("first delete",), is_delete=True)
        s2 = s1.set_unnamed(("second delete",), is_delete=True)
        assert s2.get("1").content == ("second delete",)
        assert s2.get("2").content == ("first delete",)

    def test_set_unnamed_delete_shifts_up_to_nine(self) -> None:
        store = RegisterStore()
        current = store
        for i in range(10):
            current = current.set_unnamed((f"delete-{i}",), is_delete=True)
        # Register 1 should have the latest
        assert current.get("1").content == ("delete-9",)
        # Register 9 should have delete-1 (delete-0 was shifted out)
        assert current.get("9").content == ("delete-1",)

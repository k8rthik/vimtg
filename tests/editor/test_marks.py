"""Tests for vimtg.editor.marks — vim-style mark storage."""

from vimtg.editor.marks import Mark, MarkStore


class TestSetAndGet:
    def test_set_and_get(self) -> None:
        store = MarkStore()
        updated = store.set("a", row=5, col=3)
        mark = updated.get("a")
        assert mark == Mark(row=5, col=3)

    def test_get_unset_returns_none(self) -> None:
        store = MarkStore()
        assert store.get("z") is None

    def test_set_does_not_mutate_original(self) -> None:
        store = MarkStore()
        _ = store.set("a", row=1)
        assert store.get("a") is None

    def test_set_overwrites_existing(self) -> None:
        store = MarkStore()
        s1 = store.set("a", row=1)
        s2 = s1.set("a", row=10)
        assert s2.get("a") == Mark(row=10, col=0)

    def test_default_col_zero(self) -> None:
        store = MarkStore()
        updated = store.set("a", row=3)
        assert updated.get("a") == Mark(row=3, col=0)


class TestUpdateForInsert:
    def test_marks_below_shift_down(self) -> None:
        store = MarkStore()
        s1 = store.set("a", row=5).set("b", row=10)
        updated = s1.update_for_insert(line=6, count=3)
        assert updated.get("a") == Mark(row=5, col=0)  # above — unchanged
        assert updated.get("b") == Mark(row=13, col=0)  # below — shifted

    def test_mark_at_insertion_point_shifts_down(self) -> None:
        store = MarkStore()
        s1 = store.set("a", row=5)
        updated = s1.update_for_insert(line=5, count=2)
        assert updated.get("a") == Mark(row=7, col=0)

    def test_marks_above_unchanged(self) -> None:
        store = MarkStore()
        s1 = store.set("a", row=2)
        updated = s1.update_for_insert(line=5, count=3)
        assert updated.get("a") == Mark(row=2, col=0)


class TestUpdateForDelete:
    def test_marks_in_deleted_range_removed(self) -> None:
        store = MarkStore()
        s1 = store.set("a", row=5).set("b", row=7)
        updated = s1.update_for_delete(start=4, end=8)
        assert updated.get("a") is None
        assert updated.get("b") is None

    def test_marks_below_shift_up(self) -> None:
        store = MarkStore()
        s1 = store.set("a", row=10)
        updated = s1.update_for_delete(start=3, end=5)
        # 3 lines deleted (3,4,5), so row 10 -> row 7
        assert updated.get("a") == Mark(row=7, col=0)

    def test_marks_above_unchanged(self) -> None:
        store = MarkStore()
        s1 = store.set("a", row=2)
        updated = s1.update_for_delete(start=5, end=8)
        assert updated.get("a") == Mark(row=2, col=0)

    def test_mark_at_start_boundary_removed(self) -> None:
        store = MarkStore()
        s1 = store.set("a", row=5)
        updated = s1.update_for_delete(start=5, end=7)
        assert updated.get("a") is None

    def test_mark_at_end_boundary_removed(self) -> None:
        store = MarkStore()
        s1 = store.set("a", row=7)
        updated = s1.update_for_delete(start=5, end=7)
        assert updated.get("a") is None

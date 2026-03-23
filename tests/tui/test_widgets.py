"""Tests for TUI widgets — StatusLine, CommandLine, SearchResults."""

from vimtg.tui.widgets.command_line import CommandLine
from vimtg.tui.widgets.search_results import SearchResults


def test_command_line_show_sets_prefix() -> None:
    cl = CommandLine()
    cl.show(":")
    assert cl.prefix == ":"
    assert cl.text == ""
    assert cl.message == ""


def test_command_line_hide_clears() -> None:
    cl = CommandLine()
    cl.show(":")
    cl.text = "sort"
    cl.hide()
    assert cl.prefix == ""
    assert cl.text == ""


def test_command_line_set_message_clears_prefix() -> None:
    cl = CommandLine()
    cl.show(":")
    cl.set_message("3 cards sorted")
    assert cl.message == "3 cards sorted"
    assert cl.prefix == ""


def test_search_results_select_next_clamps() -> None:
    sr = SearchResults()
    sr.results = []
    sr.select_next()
    assert sr.selected == 0


def test_search_results_select_prev_clamps() -> None:
    sr = SearchResults()
    sr.selected = 0
    sr.select_prev()
    assert sr.selected == 0


def test_search_results_get_selected_empty() -> None:
    sr = SearchResults()
    sr.results = []
    assert sr.get_selected() is None

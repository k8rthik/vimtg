"""Authoritative Textual key name → vim key name translation.

ALL Textual key events pass through translate() before reaching the keymap.
This is the single source of truth for key name mapping. No other file
should contain Textual-specific key name handling.

Textual sends verbose names for punctuation (e.g., "colon" for ":"),
but our keymap and motion registry use the actual symbols. This module
bridges that gap completely.
"""

# Complete mapping of Textual verbose key names → symbols.
# Generated from textual.keys._character_to_key for all printable chars.
_TEXTUAL_TO_SYMBOL: dict[str, str] = {
    "left_curly_bracket": "{",
    "right_curly_bracket": "}",
    "left_square_bracket": "[",
    "right_square_bracket": "]",
    "left_parenthesis": "(",
    "right_parenthesis": ")",
    "colon": ":",
    "semicolon": ";",
    "slash": "/",
    "backslash": "\\",
    "question_mark": "?",
    "exclamation_mark": "!",
    "at": "@",
    "number_sign": "#",
    "dollar_sign": "$",
    "percent_sign": "%",
    "circumflex_accent": "^",
    "ampersand": "&",
    "asterisk": "*",
    "plus": "+",
    "minus": "-",
    "equals_sign": "=",
    "less_than_sign": "<",
    "greater_than_sign": ">",
    "full_stop": ".",
    "comma": ",",
    "apostrophe": "'",
    "quotation_mark": '"',
    "underscore": "_",
    "tilde": "~",
    "grave_accent": "`",
    "vertical_line": "|",
    "space": " ",
}

# Textual modifier key normalization (ctrl+x → ctrl_x for our keymap)
_MODIFIER_NORMALIZE: dict[str, str] = {
    "ctrl+c": "ctrl_c",
    "ctrl+r": "ctrl_r",
    "ctrl+d": "ctrl_d",
    "ctrl+u": "ctrl_u",
    "ctrl+a": "ctrl_a",
    "ctrl+x": "ctrl_x",
    "ctrl+j": "ctrl_j",
    "ctrl+k": "ctrl_k",
    "ctrl+n": "ctrl_n",
    "ctrl+p": "ctrl_p",
    "ctrl+s": "ctrl_s",
    "ctrl+w": "ctrl_w",
    "shift+tab": "shift_tab",
}


def translate(textual_key: str) -> str:
    """Translate a Textual key event name to the canonical vim key name.

    This is the ONLY function that should know about Textual's key naming.
    Everything downstream uses the returned canonical name.

    Examples:
        translate("colon") → ":"
        translate("question_mark") → "?"
        translate("j") → "j"
        translate("ctrl+r") → "ctrl_r"
        translate("escape") → "escape"
        translate("enter") → "enter"
    """
    # Check symbol mapping first
    if textual_key in _TEXTUAL_TO_SYMBOL:
        return _TEXTUAL_TO_SYMBOL[textual_key]

    # Check modifier normalization
    if textual_key in _MODIFIER_NORMALIZE:
        return _MODIFIER_NORMALIZE[textual_key]

    # Pass through as-is (letters, digits, escape, enter, backspace, tab, etc.)
    return textual_key

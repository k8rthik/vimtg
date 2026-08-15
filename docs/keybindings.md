# Keybindings

vimtg ships with a vim-faithful keymap. Everything below is normal-mode unless
flagged otherwise.

## Modes

| Key | From → To | Notes |
|-----|-----------|-------|
| `i` | normal → line-edit | Edit the current line in place; on `// Key:` metadata lines only the value is editable |
| `o` | normal → insert | Open a card-search prompt below the cursor |
| `O` | normal → insert | Open a card-search prompt above the cursor |
| `a` | normal → insert | Like `o`, but appends to the same section |
| `:` | normal → command | Ex command line |
| `/` | normal → search | `:find` shorthand |
| `v` | normal → visual | Character-wise selection |
| `V` | normal → visual-line | Line-wise selection |
| `Escape` | * → normal | Exit any mode |

## Navigation

| Key | Action |
|-----|--------|
| `h` `j` `k` `l` | Left / down / up / right |
| `gg` | First line |
| `G` | Last line |
| `{count}G` | Go to line `count` |
| `w` | Next card entry |
| `b` | Previous card entry |
| `{` | Previous section header |
| `}` | Next section header |
| `Ctrl-D` | Half page down |
| `Ctrl-U` | Half page up |
| `^` | First non-blank on line |
| `$` | End of line |

## Editing

| Key | Action |
|-----|--------|
| `A` | Add/edit the card's inline comment (`// …`); confirming empty text removes it |
| `dd` | Delete current line into the unnamed register |
| `yy` | Yank current line |
| `cc` | Change current line (delete + insert) |
| `D` `Y` `C` | Operate to end of line |
| `p` | Paste below |
| `P` | Paste above |
| `+` | Increment quantity |
| `-` | Decrement quantity (deletes the line at 0) |
| `x` | Delete card at cursor |
| `.` | Repeat last change (dot repeat) |
| `u` | Undo |
| `Ctrl-R` | Redo |

### Operators + motions

`d`, `y`, `c` compose with motions: `dw` deletes a card entry, `d}` deletes to
the next section header, `y5G` yanks from cursor through line 5, etc.

### Registers

Prefix any operator with `"x` to use named register `x`:

```
"adw   delete a card into register a
"ap    paste from register a
```

## Visual mode

| Key | Action |
|-----|--------|
| `d` | Delete selection |
| `y` | Yank selection |
| `c` | Change selection |
| `>` `<` | Indent / dedent (tag indentation only) |
| `Escape` | Exit |

## Tags

Tags are deck-level annotations (`#core`, `#flex`, `#budget`). Each card line
holds a frozen set of them.

| Key | Action |
|-----|--------|
| `ta` | Prompt for tag, **a**dd to current card (or visual range) |
| `tr` | Prompt for tag, **r**emove from card |
| `tt` | Prompt for tag, **t**oggle |
| `tf` | Prompt for tag expression, apply as **f**ilter |
| `tl` | **L**ist tags with counts |
| `tc` | **C**lear all tags from current card |
| `tn` | Jump to **n**ext card sharing a tag with the cursor |
| `tp` | Jump to **p**revious tagged sibling |

## Marks

| Key | Action |
|-----|--------|
| `m{a-z}` | Set mark |
| `'{a-z}` | Jump to mark |

## Macros

| Key | Action |
|-----|--------|
| `q{reg}` | Start recording into register `{reg}`; `q` again to stop |
| `@{reg}` | Replay macro from `{reg}` |
| `@@` | Replay last macro |

## Help

| Key | Action |
|-----|--------|
| `F1` | Open full-screen help (j/k scroll, `q` to close) |
| `?` | Toggle quick-reference panel |

## Command-mode keys

While typing a `:` command:

| Key | Action |
|-----|--------|
| `Tab` | Accept current completion, advance to next |
| `Shift-Tab` | Cycle to previous completion |
| `Enter` | Execute |
| `Escape` | Cancel |

Completion is fuzzy — `:so` matches `sort` (prefix) and `:st` matches `sort`
and `stats` (subsequence).

# vimtg README demo. Regenerate from the repository root with:
#
#   uv sync && uv run vhs docs/demo.tape
#
# Needs vhs (https://github.com/charmbracelet/vhs), which needs ttyd and
# ffmpeg. Fully offline: docs/demo/setup.sh loads the small card database in
# docs/demo/cards.json into a temporary sandbox, so every run is identical.

Output docs/demo.gif

Require vimtg

Set Shell "bash"
Set Theme "Catppuccin Mocha"
Set FontSize 16
Set Width 1200
Set Height 720
Set Padding 16
Set Framerate 24
Set TypingSpeed 70ms
Set CursorBlink false

Hide
Type "source docs/demo/setup.sh && clear"
Enter
Sleep 1s
Show

# Open a 100-card Commander deck
Type "vimtg krenko.deck"
Sleep 400ms
Enter
Sleep 2s

# Move onto the commander: card details expand inline under the cursor
Type@180ms "jjjjj"
Sleep 2.5s

# Search the card database: Goblins that make tokens (Tab cycles matches)
Type "o"
Sleep 400ms
Type "t:goblin o:token"
Sleep 1.2s
Tab
Sleep 900ms
Tab
Sleep 900ms
Tab
Sleep 1.2s
Escape
Sleep 600ms

# Find a card in the deck, vim style
Type "/rabble"
Sleep 400ms
Enter
Sleep 2s

# Mana curve, types, mana base and Commander bracket
Type ":analytics"
Sleep 400ms
Enter
Sleep 4s
Type ":close"
Enter
Sleep 600ms

# Goldfish a seeded opening hand, then draw two cards
Type ":hand 10"
Sleep 400ms
Enter
Sleep 3s
Type "n"
Sleep 1.2s
Type "n"
Sleep 2s
Type "q"
Sleep 800ms

# Quit
Type ":q"
Sleep 400ms
Enter
Sleep 1s

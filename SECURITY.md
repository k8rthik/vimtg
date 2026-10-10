# Security policy

## Supported versions

Security fixes land on `main` and ship in the next release; only the
latest release is supported.

| Version | Supported |
|---|---|
| latest release | yes |
| anything older | no — please upgrade |

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately through GitHub:
[**Report a vulnerability**](https://github.com/k8rthik/vimtg/security/advisories/new)
(the *Security* tab → *Advisories* → *Report a vulnerability*).

Include what you found, how to reproduce it (a deck file, URL, or command),
the vimtg version (`vimtg --version`), and your OS. You should get an
acknowledgement within a week. Once a fix is released the advisory is
published with credit to you, unless you prefer otherwise.

## Scope

Things that are in scope include, for example:

- Opening or importing a crafted `.deck`, `.dek`, CSV, or text file (or a
  deck URL) that causes code execution, writes outside the intended
  location, or corrupts other decks or the card database.
- Unsafe handling of responses from Scryfall, EDHREC, or the deck-site
  importers (Moxfield, Archidekt, Deckstats, TappedOut, MTGGoldfish).
- Terminal escape-sequence injection from card or deck data (including the
  OSC 52 clipboard path).

vimtg sends no telemetry and needs no credentials; see the
[network and privacy](https://github.com/k8rthik/vimtg#network-and-privacy)
section of the README for every request it makes.

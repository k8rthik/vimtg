# Sourced (off camera) by docs/demo.tape. Builds a throwaway, offline vimtg
# sandbox so the recording never touches your real card database or decks.
demo_src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
demo_dir="$(mktemp -d)"
export XDG_DATA_HOME="$demo_dir/data" XDG_CACHE_HOME="$demo_dir/cache"
export XDG_CONFIG_HOME="$demo_dir/config" XDG_STATE_HOME="$demo_dir/state"
export VIMTG_NO_AUTOSYNC=1 VIMTG_NO_EDHREC=1
# A fresh oracle_cards.json in the cache is what `vimtg sync` loads instead
# of downloading, so the demo card data is exactly docs/demo/cards.json.
mkdir -p "$XDG_CACHE_HOME/vimtg"
cp "$demo_src/cards.json" "$XDG_CACHE_HOME/vimtg/oracle_cards.json"
vimtg sync >/dev/null
cp "$demo_src/krenko.deck" "$demo_dir/"
cd "$demo_dir" || return
export PS1='$ '

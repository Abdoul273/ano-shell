#!/usr/bin/env sh

cat ~/.local/state/ano-shell/sequences.txt 2>/dev/null

exec "$@"

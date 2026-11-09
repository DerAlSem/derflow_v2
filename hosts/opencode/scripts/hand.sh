#!/usr/bin/env bash
# Точка входа расщепления для OpenCode: движок общий — ~/.zcode/scripts/hand.sh,
# здесь только цель. Канон хендоффа — derflow/_capture.md (~/.claude).
export HAND_CLIENT=opencode
exec "${HOME}/.zcode/scripts/hand.sh" "$@"

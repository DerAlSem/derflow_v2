#!/usr/bin/env bash
# Тесты bl-lock.sh на временном git-окружении (DK-11, RFC agent-sessions
# v2 §3.1/§18A). Живые сессии не нужны: ZCODE_SESSION_ID подставляется env.
#   ./test-bl-lock.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail=0
ok()  { echo "✅ $*"; }
bad() { echo "❌ $*"; fail=1; }

# Временное окружение: git-репо + стаб backlog впереди PATH.
env_dir="$(mktemp -d)"
trap 'rm -rf "$env_dir"' EXIT
bin="$env_dir/bin"; mkdir "$bin"
cat > "$bin/backlog" <<'STUB'
#!/usr/bin/env bash
echo "stub: backlog $*" >> "${STUB_LOG:-/dev/null}"
echo "ok"
STUB
chmod +x "$bin/backlog"
repo="$env_dir/repo"
git init -q -b main "$repo"
git -C "$repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
# macOS: mktemp отдаёт /var/..., git — физический /private/var/...
repo_real="$(cd "$repo" && pwd -P)"

# run <cwd> [присвоения/env-флаги...] -- <аргументы bl-lock.sh>
run() {
  local wd="$1"; shift
  local -a pre=()
  while [ "$1" != -- ]; do pre+=("$1"); shift; done
  shift
  ( cd "$wd" && env ${pre[@]+"${pre[@]}"} PATH="$bin:$PATH" \
      "$here/bl-lock.sh" "$@" )
}
locks="$repo/.git/bl-locks"
owner_of() { cat "$locks/$1/owner"; }

# AC#1: переменная есть → owner содержит session: + прежние поля
run "$repo" ZCODE_SESSION_ID=sess_1111 -- take T1 alice >/dev/null
o="$(owner_of T1)"
for line in 'who: alice' 'branch: main' "tree: $repo_real" 'session: sess_1111'; do
  grep -qx "$line" <<<"$o" && ok "T1 owner: $line" || bad "T1 owner нет: $line"
done
grep -Eq '^since: [0-9]+$' <<<"$o" && ok "T1 owner: since — число" \
  || bad "T1 owner: since не число"

# AC#2: переменной нет / пуста → строки session: нет, take не меняется
run "$repo" -u ZCODE_SESSION_ID -- take T2u bob >/dev/null
o="$(owner_of T2u)"
grep -q '^session:' <<<"$o" && bad "T2u: session: появился без переменной" \
  || ok "T2u: переменной нет — session: нет"
run "$repo" ZCODE_SESSION_ID= -- take T2e carol >/dev/null
o="$(owner_of T2e)"
grep -q '^session:' <<<"$o" && bad "T2e: session: появился при пустой" \
  || ok "T2e: переменная пуста — session: нет"

# AC#3: старый формат owner без session: валиден, who и drop без миграции
mkdir -p "$locks/T3"
printf 'who: dave\nbranch: main\ntree: %s\nsince: 100\n' "$repo" > "$locks/T3/owner"
run "$repo" -u ZCODE_SESSION_ID -- who | grep -q '^T3 · dave ·' \
  && ok "T3: who видит старый замок" || bad "T3: who сломался на старом формате"
o="$(owner_of T3)"
run "$repo" -u ZCODE_SESSION_ID -- drop T3 >/dev/null
[ ! -e "$locks/T3" ] && ok "T3: drop старого замка без миграции" \
  || bad "T3: drop старого замка не сработал"

# AC#4: конфликт — код 3, чужой owner (и его session:) не перезаписан
run "$repo" ZCODE_SESSION_ID=sess_a -- take T4 eve >/dev/null
if run "$repo" ZCODE_SESSION_ID=sess_b -- take T4 mallory >/dev/null 2>&1; then
  bad "T4: второй take прошёл вместо конфликта"
else
  rc=$?
  [ "$rc" -eq 3 ] && ok "T4: конфликт с кодом 3" || bad "T4: код $rc вместо 3"
fi
o="$(owner_of T4)"
grep -qx 'session: sess_a' <<<"$o" && ok "T4: чужой session: цел" \
  || bad "T4: чужой session: перезаписан"
grep -qx 'who: eve' <<<"$o" && ok "T4: чужой who цел" || bad "T4: чужой who перезаписан"

# AC#5: два take в одной сессии → одинаковый ID, состояние раздельно
run "$repo" ZCODE_SESSION_ID=sess_same -- take T5a frank >/dev/null
run "$repo" ZCODE_SESSION_ID=sess_same -- take T5b grace >/dev/null
grep -qx 'session: sess_same' <<<"$(owner_of T5a)" \
  && grep -qx 'session: sess_same' <<<"$(owner_of T5b)" \
  && ok "T5: один ID в обоих замках" || bad "T5: ID разошёлся по замкам"
grep -qx 'who: grace' <<<"$(owner_of T5b)" && ok "T5: владельцы независимы" \
  || bad "T5: замки слились"

# AC#6: release удаляет замок целиком, исторической записи нет
run "$repo" -- release T5a
[ ! -e "$locks/T5a" ] && ok "T5a: release — замка нет" \
  || bad "T5a: release оставил след"
[ -e "$locks/T5a/session" ] && bad "T5a: история сессии сохранилась"

# AC#1 (хвост): who не ломается на замке с session:
run "$repo" ZCODE_SESSION_ID=sess_1111 -- who >/dev/null \
  && ok "who: замки с session: читаются" || bad "who: упал на session:"

[ "$fail" -eq 0 ] && echo "все тесты зелёные" || { echo "есть красные"; exit 1; }

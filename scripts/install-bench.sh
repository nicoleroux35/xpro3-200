#!/usr/bin/env bash
# Install the X-Pro3 bench into a FujiMod checkout.
#
# The bench is a workspace member of the emulator it drives, so it is installed
# rather than vendored: one copy of the emulator, one copy of the bench, no
# duplicated crates and no fork.
#
# Usage:
#   ./scripts/install-bench.sh PATH/TO/FUJIMOD
#
# What it does:
#   1. checks the target is a FujiMod checkout
#   2. copies bench/xpro3-bench      -> TARGET/apps/xpro3-bench
#   3. copies configs/*              -> TARGET/configurations/emulator/
#   4. adds "apps/xpro3-bench" to the workspace members in TARGET/Cargo.toml
#   5. prints the next command
#
# It refuses to overwrite an existing apps/xpro3-bench with different content
# unless --force is given.

set -euo pipefail

force=0
args=()
for arg in "$@"; do
  case "$arg" in
    --force) force=1 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) args+=("$arg") ;;
  esac
done

if [[ ${#args[@]} -ne 1 ]]; then
  echo "usage: $0 PATH/TO/FUJIMOD [--force]" >&2
  exit 2
fi

here=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
target=$(cd "${args[0]}" 2>/dev/null && pwd) || { echo "$0: no such directory: ${args[0]}" >&2; exit 2; }

# 1. Is this a FujiMod checkout?
if [[ ! -f "$target/Cargo.toml" || ! -d "$target/crates/emulator-boot" ]]; then
  echo "$0: $target does not look like a FujiMod checkout" >&2
  echo "     expected Cargo.toml and crates/emulator-boot" >&2
  exit 2
fi

# 2. Bench crate.
dest="$target/apps/xpro3-bench"
if [[ -e "$dest" ]]; then
  if diff -rq "$here/bench/xpro3-bench" "$dest" >/dev/null 2>&1; then
    echo "bench: already installed and identical"
  elif [[ $force -eq 1 ]]; then
    echo "bench: replacing $dest (--force)"
    rm -rf "$dest"
    cp -r "$here/bench/xpro3-bench" "$dest"
  else
    echo "$0: $dest already exists and differs; pass --force to replace" >&2
    exit 2
  fi
else
  mkdir -p "$target/apps"
  cp -r "$here/bench/xpro3-bench" "$dest"
  echo "bench: installed to $dest"
fi

# 3. Run configurations. `body-profiles.json` is not a configuration, so it is
# skipped by the glob below and merged into the body record in step 3b.
mkdir -p "$target/configurations/emulator"
for config in "$here"/configs/*/; do
  name=$(basename "$config")
  cp -r "$config" "$target/configurations/emulator/$name"
  echo "config: installed $name"
done

# 3b. The body profile the configuration names. Upstream's xpro3 body has no
# hardware.profiles entry, so the run is rejected with
# "body xpro3 has no hardware profile xpro3-200-handoff" until it is merged in.
python3 - "$target/catalog/bodies/xpro3/body.json" "$here/configs/body-profiles.json" <<'PY'
import json
import sys
from pathlib import Path

body_path, profiles_path = Path(sys.argv[1]), Path(sys.argv[2])
if not body_path.exists():
    raise SystemExit("body: %s not found; is this a FujiMod checkout?" % body_path)

body = json.loads(body_path.read_text())
profiles = json.loads(profiles_path.read_text())["hardware"]["profiles"]
existing = body.setdefault("hardware", {}).setdefault("profiles", {})

added = []
for name, profile in profiles.items():
    if existing.get(name) == profile:
        continue
    existing[name] = profile
    added.append(name)

if not added:
    print("body: profile already present")
else:
    body_path.write_text(json.dumps(body, indent=2) + "\n")
    print("body: added profile(s) %s" % ", ".join(added))
PY

# 4. Workspace member.
python3 - "$target/Cargo.toml" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text().splitlines(keepends=True)
member = 'apps/xpro3-bench'

if any(line.strip().strip('",') == member for line in lines):
    print("workspace: already a member")
    raise SystemExit(0)

start = next((i for i, line in enumerate(lines) if line.strip().startswith('members = [')), None)
if start is None:
    raise SystemExit("workspace: no members list found; add %r by hand" % member)

# Find the closing bracket of the members list.
end = next((i for i in range(start, len(lines)) if lines[i].strip() == ']'), None)
if end is None:
    raise SystemExit("workspace: members list is not closed with ']'")

lines.insert(end, '  "%s",\n' % member)
path.write_text(''.join(lines))
print("workspace: added %s" % member)
PY

cat <<EOF

Installed. Next:

  cd $target
  cargo build -p fujimod-xpro3-bench

The emulator vendors Unicorn as a git submodule; if this checkout was cloned
without it, run:  git submodule update --init --recursive

The bench needs the Fujifilm X-Pro3 2.00 update (FWUP0021.DAT) and a plan:

  python3 $here/tools/generate_xpro3_plan.py \\
    --fujimod $target \\
    --firmware-dir /path/to/firmware-dir \\
    --output /tmp/xpro3-plan.json

  cargo run -p fujimod-xpro3-bench -- \\
    --update /path/to/FWUP0021.DAT \\
    --application-plan /tmp/xpro3-plan.json \\
    --discovery --poke 0xa2ec=4
EOF
#!/usr/bin/env bash
# Builds the image and checks the things that used to be broken about it:
# it must start without the Windows only packages, it must not hang waiting for
# an answer nobody is there to give, and it must not carry anyone's cookie.
#
# Used by the CI workflow and runnable by hand:  bash scripts/check-docker.sh
set -u

IMAGE="${IMAGE:-steamgiftbot:check}"
failures=0

report() {
    if [ "$1" = "0" ]; then
        printf '  PASS  %s\n' "$2"
    else
        printf '  FAIL  %s\n' "$2"
        failures=$((failures + 1))
    fi
}

expectCode() {
    local wanted="$1" label="$2"; shift 2
    local output code
    output=$(timeout 120 docker run --rm "$@" 2>&1)
    code=$?
    if [ "$code" = "$wanted" ]; then
        report 0 "$label (exit $code)"
    else
        report 1 "$label (wanted exit $wanted, got $code)"
        printf '        %s\n' "$(printf '%s' "$output" | tail -2)"
    fi
}

echo "Building $IMAGE"
if ! docker build -t "$IMAGE" . ; then
    echo "  FAIL  the image does not build"
    exit 1
fi
echo

echo "Checks"

# The entry point is 'python main.py --no-input', so this reaches argparse.
expectCode 0 "--version answers"                         "$IMAGE" --version

# The old image died here: an interactive prompt with nobody to answer it.
expectCode 2 "an empty setup fails instead of hanging"   "$IMAGE" --once

expectCode 2 "--notify-test with no destination fails"   "$IMAGE" --notify-test

# Settings arrive through the environment, so this must get past setup and only
# then fail on the fake cookie.
expectCode 1 "a full setup gets as far as the cookie" \
    -e STEAMGIFTBOT_COOKIE=not_a_real_session \
    -e STEAMGIFTBOT_GIFT_TYPE=All \
    -e STEAMGIFTBOT_MIN_POINTS=0 \
    -e STEAMGIFTBOT_PINNED=no \
    -e STEAMGIFTBOT_CHECK_WINS=no \
    "$IMAGE" --once --dry-run

# keyboard and clipboard are Windows only now; importing them on Linux used to
# stop the container before it printed anything.
if docker run --rm --entrypoint python "$IMAGE" -c "
import steamgiftbot.cli, steamgiftbot.ui
assert steamgiftbot.ui.PASTE_HOTKEY is False
print('ok')" >/dev/null 2>&1; then
    report 0 "the package imports without keyboard and clipboard"
else
    report 1 "the package imports without keyboard and clipboard"
fi

# A config.ini or a state file baked into a published image would hand out a
# session cookie to everyone who pulls it.
leaked=$(docker run --rm --entrypoint sh "$IMAGE" -c \
    "ls -A /app | grep -E '^(config\.ini|steamgiftbot-state\.json|\.env)$' | wc -l" 2>/dev/null)
report "$([ "${leaked:-1}" = "0" ] && echo 0 || echo 1)" "no cookie or state baked into the image"

# Tests and CI files have no business being shipped.
extra=$(docker run --rm --entrypoint sh "$IMAGE" -c \
    "ls -A /app | grep -E '^(tests|\.git|\.github)$' | wc -l" 2>/dev/null)
report "$([ "${extra:-1}" = "0" ] && echo 0 || echo 1)" "no tests or repository files shipped"

size=$(docker image inspect "$IMAGE" --format '{{.Size}}' 2>/dev/null)
[ -n "$size" ] && printf '\n  image size: %s MB\n' "$((size / 1024 / 1024))"

echo
if [ "$failures" = "0" ]; then
    echo "All Docker checks passed."
    exit 0
fi
echo "$failures Docker check(s) failed."
exit 1

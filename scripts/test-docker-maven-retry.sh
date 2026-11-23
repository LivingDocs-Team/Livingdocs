#!/bin/sh
# Exercise the actual Dockerfile commands with Maven and sleep replaced.
set -eu
cd "$(dirname "$0")/.."
tmp="$(mktemp -d)"
trap 'rm -f "$tmp/mvn" "$tmp/sleep" "$tmp/trace" "$tmp/build.sh" "$tmp/output"; rmdir "$tmp"' EXIT
export RETRY_TRACE="$tmp/trace"
export PATH="$tmp:$PATH"

cat >"$tmp/mvn" <<'EOF'
#!/bin/sh
attempt="$(grep -c '^mvn$' "$RETRY_TRACE" || true)"
echo mvn >>"$RETRY_TRACE"
case "$RETRY_CASE" in
    success) exit 0 ;;
    recovery) [ "$attempt" -ge 2 ] && exit 0 ;;
    unrelated) echo 'Compilation failure'; exit 17 ;;
    timeout) echo 'Read timed out while contacting Maven Central'; exit 124 ;;
    other_registry) echo 'from/to mirror (https://example.test/maven2): status code: 429'; exit 19 ;;
esac
echo 'from/to central (https://repo.maven.apache.org/maven2): status code: 429, reason phrase: Too Many Requests'
exit 23
EOF
cat >"$tmp/sleep" <<'EOF'
#!/bin/sh
echo "sleep $1" >>"$RETRY_TRACE"
EOF
chmod +x "$tmp/mvn" "$tmp/sleep"

check() {
    export RETRY_CASE="$1"
    expected_status="$2"
    expected_trace="$3"
    : >"$RETRY_TRACE"
    status=0
    sh "$tmp/build.sh" >"$tmp/output" 2>&1 || status=$?
    if [ "$status" -ne "$expected_status" ] || [ "$(paste -sd, "$RETRY_TRACE")" != "$expected_trace" ]; then
        echo "$dockerfile: $RETRY_CASE failed (exit $status)" >&2
        cat "$RETRY_TRACE" "$tmp/output" >&2
        exit 1
    fi
}

for dockerfile in backend/Dockerfile services/github-integration-service/Dockerfile; do
    sed -n "/^RUN .*<<'MAVEN_BUILD'$/,/^MAVEN_BUILD$/p" "$dockerfile" | sed '1d;$d' >"$tmp/build.sh"
    test -s "$tmp/build.sh"
    check success 0 'mvn'
    check recovery 0 'mvn,sleep 5,mvn,sleep 10,mvn'
    check exhausted 23 'mvn,sleep 5,mvn,sleep 10,mvn,sleep 20,mvn'
    check unrelated 17 'mvn'
    check timeout 124 'mvn'
    check other_registry 19 'mvn'
    echo "$dockerfile: all retry cases passed"
done

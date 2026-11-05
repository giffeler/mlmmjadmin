#!/usr/bin/env bash
# Create and destroy a private test database; never use a system datadir.
set -euo pipefail
if [[ "$(id -u)" == 0 ]]; then
    echo 'Run as an unprivileged user; the permission tests must not run as root.' >&2
    exit 1
fi
socket_test_python="${SOCKET_TEST_PYTHON:?Set SOCKET_TEST_PYTHON to the test virtualenv interpreter}"
socket_test_root="$(mktemp -d /tmp/mail-sql.XXXXXX)"
socket_test_pid=''
cleanup() {
    if [[ -n "$socket_test_pid" ]]; then
        kill "$socket_test_pid" 2>/dev/null || true
        wait "$socket_test_pid" 2>/dev/null || true
    fi
    rm -rf -- "$socket_test_root"
}
trap cleanup EXIT
mariadb-install-db --no-defaults --datadir="$socket_test_root/data"     --auth-root-authentication-method=normal --skip-test-db >"$socket_test_root/init.log" 2>&1
socket_test_path="$socket_test_root/db.sock"
start_database() {
    mariadbd --no-defaults --datadir="$socket_test_root/data"         --socket="$socket_test_path" --pid-file="$socket_test_root/db.pid"         --log-error="$socket_test_root/error.log" --skip-log-bin "$@" &
    socket_test_pid=$!
    for attempt in {1..60}; do
        if mariadb-admin --no-defaults --socket="$socket_test_path" --user=root ping >/dev/null 2>&1; then
            return
        fi
        if ! kill -0 "$socket_test_pid" 2>/dev/null; then
            cat "$socket_test_root/error.log" >&2
            exit 1
        fi
        sleep 1
    done
    cat "$socket_test_root/error.log" >&2
    exit 1
}
start_database --skip-networking
mariadb --no-defaults --socket="$socket_test_path" --user=root <<'SQL'
CREATE DATABASE socket_test;
CREATE USER 'socket_test'@'localhost' IDENTIFIED BY 'isolated-test-password';
CREATE USER 'socket_test'@'127.0.0.1' IDENTIFIED BY 'isolated-test-password';
GRANT ALL ON socket_test.* TO 'socket_test'@'localhost';
GRANT ALL ON socket_test.* TO 'socket_test'@'127.0.0.1';
SELECT VERSION(), @@skip_networking;
SQL

# The CI runner can test with the application's service-account name and a
# dedicated socket-access group. These are disposable runner accounts only.
if [[ -n "${SOCKET_TEST_USER:-}" ]]; then
    if [[ "${GITHUB_ACTIONS:-}" != true ]]; then
        echo 'Service-account setup is restricted to disposable GitHub Actions runners.' >&2
        exit 1
    fi
    sudo groupadd -f socketdb-test
    id "$SOCKET_TEST_USER" >/dev/null 2>&1 || sudo useradd --system --no-create-home "$SOCKET_TEST_USER"
    sudo usermod -a -G socketdb-test "$SOCKET_TEST_USER"
    sudo chgrp socketdb-test "$socket_test_root"
    chmod 750 "$socket_test_root"
    sudo chgrp socketdb-test "$socket_test_path"
    chmod 660 "$socket_test_path"
fi
run_tests() {
    if [[ -n "${SOCKET_TEST_USER:-}" ]]; then
        sudo -u "$SOCKET_TEST_USER" env PYTHONDONTWRITEBYTECODE=1             SOCKET_TEST_PATH="$socket_test_path"             SOCKET_TEST_TCP_PORT="${SOCKET_TEST_TCP_PORT:-}"             "$socket_test_python" -m pytest -q -p no:cacheprovider downstream_tests "$@"
    else
        SOCKET_TEST_PATH="$socket_test_path"             "$socket_test_python" -m pytest -q -p no:cacheprovider downstream_tests "$@"
    fi
}
run_tests

# Exercise the existing TCP/TLS paths in the same disposable database.
kill "$socket_test_pid"
wait "$socket_test_pid"
socket_test_pid=''
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=localhost'     -keyout "$socket_test_root/server.key" -out "$socket_test_root/server.crt" >/dev/null 2>&1
SOCKET_TEST_TCP_PORT="$($socket_test_python -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
export SOCKET_TEST_TCP_PORT
start_database --bind-address=127.0.0.1 --port="$SOCKET_TEST_TCP_PORT"     --ssl-key="$socket_test_root/server.key" --ssl-cert="$socket_test_root/server.crt"     --ssl-ca="$socket_test_root/server.crt"
run_tests -k 'live_tcp or missing_socket or inaccessible_socket'

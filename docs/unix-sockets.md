# MySQL/MariaDB Unix sockets

This downstream branch adds optional explicit Unix-domain socket transport. It is not an upstream release. The implementation forwards the driver's supported `unix_socket` parameter; bundled third-party libraries are unchanged.

## Configuration

All socket settings default to `''`. Set only those relevant to the enabled MySQL databases in `settings.py`:

```python
iredmail_sql_db_socket = '/run/mysqld/mysqld.sock'
```

Use an absolute path. Absent, empty, or `None` settings retain the existing TCP path. A nonempty invalid value produces a configuration error. When a socket is selected, TCP host and port settings are not read or converted. Missing or inaccessible sockets fail at connection time, with no TCP fallback. SQLAlchemy and web.py connect lazily, so constructing a connection factory alone does not prove connectivity.

Existing database usernames, passwords, and privileges remain in use. This feature does not enable MariaDB's `unix_socket` authentication plugin. Existing SQL authentication grants must permit the local connection.

## TLS and PostgreSQL

A nonempty MySQL socket setting explicitly selects local filesystem transport. TCP-only `*_db_use_ssl` settings are unused in this mode and are not forwarded to the driver; no TLS channel is requested over the socket. Filesystem permissions and database authentication apply. Empty socket settings preserve the existing TCP/TLS options exactly, including their existing certificate-validation policy. This extension does not strengthen or weaken that pre-existing TCP policy.

PostgreSQL ignores the MySQL socket settings, and its existing behavior is preserved. No MySQL-specific socket parameter is passed to PostgreSQL.

## Filesystem access

On Linux, the service account needs traversal permission on every parent directory and permission to connect to the socket (normally write permission on the socket). Give only the required service accounts access, using a dedicated group or suitable ACLs; do not make a database data directory broadly accessible. Check ownership/mode again after a database restart because its socket is recreated. Service sandboxing, AppArmor/SELinux rules, and namespaces can impose additional restrictions.

Configure and test all database clients before enabling MariaDB `skip-networking`. A privileged interactive shell is not evidence that the actual service account can connect.

## Coverage and scope

The MySQL backend factory supports socket mode. PGSQLWrap is unchanged. Tests exercise domain and mailing-list existence queries against a minimal isolated SQL fixture; they are not a complete mailing-list lifecycle or REST API test.

The test suite uses temporary settings and a disposable database. It never loads production configuration. Application logging is redirected to the test logger. PostgreSQL checks verify argument isolation and unchanged factories without connecting to a live PostgreSQL server. Full SMTP policy behavior, complete application workflows, the target server's service sandboxing, and production rollback remain staging/operational acceptance tasks.

## Reproducing validation

Create a Python 3.12 virtual environment and install `downstream_tests/requirements.txt` plus SQLAlchemy 2.0.57 (or 1.4.54 for the iRedAPD compatibility run). From this repository:

```sh
python -m pytest -q downstream_tests
```

This runs local regressions and explicitly skips tests requiring a database. To run integration tests on a disposable Linux machine with MariaDB server/client binaries and OpenSSL installed, as a non-root user:

```sh
SOCKET_TEST_PYTHON=/absolute/path/to/venv/bin/python bash downstream_tests/run-mariadb.sh
```

The runner creates its own temporary data directory, starts MariaDB with `--skip-networking`, and verifies real AF_UNIX connections, queries, and error behavior. It then restarts only that private instance with loopback TCP and a temporary certificate to exercise the existing TCP/TLS paths. It cleans up its own instance and data on exit. It never starts, stops, or reconfigures a system database service.

GitHub Actions tests both the runner distribution's MariaDB and the official `mariadb:11.8.6` image. The optional `SOCKET_TEST_IMAGE` runner setting selects an installed Docker image, mounting only the disposable database directory. Clients remain outside the container so Linux socket permissions are tested across the mount.

GitHub Actions additionally runs clients under a disposable service-named account with a dedicated socket-access group. These runner accounts model permission boundaries; they are not evidence of the target server's actual UID/group membership or sandbox configuration. Test credentials and SQL fixtures are disposable and must never be used for deployment.

See [downstream maintenance](downstream-maintenance.md) for upgrade and rollback preparation.

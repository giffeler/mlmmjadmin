"""Connection-path regressions against the bundled adapters and real drivers."""
import os
import socket
from types import SimpleNamespace

import pytest
from conftest import PROJECT, settings
from libs.sql_transport import describe_transport, mysql_socket, web_transport
from pymysql.err import OperationalError
from sqlalchemy.exc import OperationalError as SAOperationalError


def connection_options(conn, kind):
    assert conn is not None
    if kind == 'engine':
        _args, options = conn.dialect.create_connect_args(conn.url)
        return options
    return conn.keywords


def query(conn, kind, sql):
    if kind == 'engine':
        with conn.connect() as db:
            return db.exec_driver_sql(sql).scalar()
    return next(iter(conn.query(sql)))['result']


def close(conn, kind):
    if kind == 'engine':
        conn.dispose()
    elif conn._ctx.get('db'):
        conn._ctx.db.close()
        conn._ctx.clear()


def test_socket_ignores_absent_host_and_bad_port(factory):
    name, kind, make = factory
    for suffix in ['host', 'server']:
        delattr(settings, name + '_db_' + suffix)
    setattr(settings, name + '_db_port', 'not-a-port')
    conn = make()
    options = connection_options(conn, kind)
    assert options.get('host') in (None, '')
    assert options.get('port') in (None, 0)
    if kind != 'engine':
        assert options['unix_socket'] == getattr(settings, name + '_db_socket')
    close(conn, kind)


@pytest.mark.parametrize('configured', [False, True])
def test_tcp_defaults_are_preserved(factory, configured):
    name, kind, make = factory
    if configured:
        setattr(settings, name + '_db_socket', '')
    else:
        delattr(settings, name + '_db_socket')
    setattr(settings, name + '_db_port', '13306')
    conn = make()
    options = connection_options(conn, kind)
    assert options['host'] == '127.0.0.1'
    assert options['port'] == 13306
    assert 'unix_socket' not in options
    close(conn, kind)


def test_missing_socket_never_attempts_tcp(factory, tmp_path, monkeypatch):
    name, kind, make = factory
    setattr(settings, name + '_db_socket', str(tmp_path / 'missing.sock'))
    attempted = []
    original = socket.socket.connect

    def checked(sock, address):
        attempted.append(sock.family)
        assert sock.family == socket.AF_UNIX, 'Unexpected TCP fallback'
        return original(sock, address)

    monkeypatch.setattr(socket.socket, 'connect', checked)
    conn = make()
    with pytest.raises((OperationalError, SAOperationalError), match='No such file|2002|2003'):
        query(conn, kind, 'SELECT 1 AS result')
    assert attempted and set(attempted) == {socket.AF_UNIX}
    close(conn, kind)


def test_inaccessible_socket_never_attempts_tcp(factory, tmp_path, monkeypatch):
    if os.geteuid() == 0:
        pytest.skip('Filesystem permission test requires an unprivileged user')
    name, kind, make = factory
    private = tmp_path / 'private'
    private.mkdir()
    path = private / 'database.sock'
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(path))
    listener.listen(1)
    setattr(settings, name + '_db_socket', str(path))
    attempted = []
    original = socket.socket.connect

    def checked(sock, address):
        attempted.append(sock.family)
        assert sock.family == socket.AF_UNIX, 'Unexpected TCP fallback'
        return original(sock, address)

    monkeypatch.setattr(socket.socket, 'connect', checked)
    private.chmod(0)
    conn = make()
    try:
        with pytest.raises((OperationalError, SAOperationalError), match='Permission denied|13'):
            query(conn, kind, 'SELECT 1 AS result')
        assert attempted and set(attempted) == {socket.AF_UNIX}
    finally:
        private.chmod(0o700)
        listener.close()
        close(conn, kind)


def test_socket_tls_policy(factory):
    name, kind, make = factory
    setattr(settings, name + '_db_use_ssl', True)
    conn = make()
    options = connection_options(conn, kind)
    assert not any(key.startswith('ssl') for key in options)
    close(conn, kind)


@pytest.mark.parametrize('dbn', ['postgres', 'postgresql'])
def test_postgres_transport_ignores_mysql_socket(dbn):
    config = SimpleNamespace(test_db_socket=123, test_db_server='127.0.0.1',
                             test_db_port='5432', test_db_use_ssl=True)
    assert mysql_socket(config, 'test', dbn) == ''
    assert web_transport(config, 'test', dbn, with_ssl=True) == {
        'host': '127.0.0.1', 'port': 5432, 'sslmode': 'prefer'}


def test_tcp_ssl_options_preserved():
    config = SimpleNamespace(test_db_server='127.0.0.1', test_db_port='3306',
                             test_db_use_ssl=True)
    assert web_transport(config, 'test', 'mysql', with_ssl=True)['ssl'] == {'ssl': True}
    assert 'ssl' not in web_transport(config, 'test', 'mysql')


@pytest.mark.parametrize('value', ['relative.sock', False, 42])
def test_bad_socket_configuration_reports_setting(value):
    with pytest.raises(ValueError, match='test_db_socket'):
        mysql_socket(SimpleNamespace(test_db_socket=value), 'test', 'mysql')


def test_endpoint_logging_needs_no_tcp_settings():
    assert describe_transport(SimpleNamespace(test_db_socket='/tmp/local.sock'),
                              'test', 'mysql') == 'Unix socket /tmp/local.sock'


def test_real_socket_transport(factory, live_database, monkeypatch):
    name, kind, make = factory
    for suffix in ['server', 'host', 'port']:
        delattr(settings, name + '_db_' + suffix)
    connected = []
    original = socket.socket.connect

    def checked(sock, address):
        assert sock.family == socket.AF_UNIX
        result = original(sock, address)
        connected.append(sock.family)
        return result

    monkeypatch.setattr(socket.socket, 'connect', checked)
    conn = make()
    try:
        assert query(conn, kind, 'SELECT @@skip_networking AS result') == 1
        assert query(conn, kind, 'SELECT 42 AS result') == 42
        assert connected and set(connected) == {socket.AF_UNIX}
        if kind == 'engine':
            with conn.connect() as db:
                assert db.connection._sock.family == socket.AF_UNIX
        else:
            assert conn.ctx.db._sock.family == socket.AF_UNIX
    finally:
        close(conn, kind)


def test_ldap_auxiliary_socket(factory):
    if PROJECT == 'mlmmjadmin':
        pytest.skip('This backend selects SQL independently of an LDAP account backend')
    name, kind, make = factory
    if name == 'vmail':
        pytest.skip('LDAP account data is not a MySQL auxiliary database')
    settings.backend = 'ldap'
    for suffix in ['host', 'server', 'port']:
        delattr(settings, name + '_db_' + suffix)
    conn = make()
    assert conn is not None
    if kind != 'engine':
        assert conn.keywords['unix_socket'] == getattr(settings, name + '_db_socket')
    close(conn, kind)


def test_live_tcp_and_existing_tls(factory):
    import ssl
    port = os.environ.get('SOCKET_TEST_TCP_PORT')
    if not port:
        pytest.skip('TCP/TLS phase of the isolated MariaDB runner')
    name, kind, make = factory
    setattr(settings, name + '_db_socket', '')
    setattr(settings, name + '_db_port', port)
    setattr(settings, name + '_db_use_ssl', True)
    conn = make()
    try:
        assert query(conn, kind, 'SELECT 42 AS result') == 42
        if kind == 'engine':
            raw = conn.raw_connection()
            dbapi = raw
        else:
            raw = None
            dbapi = conn.ctx.db
        assert dbapi._sock.family == socket.AF_INET
        tls_expected = (PROJECT == 'iRedAPD' and kind in ['engine', 'tools']) or PROJECT == 'mlmmjadmin'
        if tls_expected:
            assert isinstance(dbapi._sock, ssl.SSLSocket)
            assert dbapi._sock.cipher()
        if raw is not None:
            raw.close()
    finally:
        close(conn, kind)

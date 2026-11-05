from backends import bk_iredmail_sql as backend
from conftest import settings


def test_postgres_wrapper_unchanged():
    settings.iredmail_sql_db_use_ssl = True
    wrapper = backend.PGSQLWrap()
    assert 'unix_socket' not in wrapper.conn.keywords
    assert wrapper.conn.keywords['sslmode'] == 'prefer'
    wrapper.conn = None


def test_tcp_tls_unchanged():
    settings.iredmail_sql_db_socket = ''
    settings.iredmail_sql_db_use_ssl = True
    conn = backend.MYSQLWrap._MYSQLWrap__connect()
    assert conn.keywords['ssl'] == {'ssl': True}


def test_mailing_list_queries_over_socket(live_database):
    conn = backend.MYSQLWrap._MYSQLWrap__connect()
    conn.query('CREATE TABLE IF NOT EXISTS domain (domain VARCHAR(255))')
    conn.query('CREATE TABLE IF NOT EXISTS alias_domain (alias_domain VARCHAR(255), target_domain VARCHAR(255))')
    conn.query('CREATE TABLE IF NOT EXISTS maillists (address VARCHAR(255))')
    for table in ['domain', 'alias_domain', 'maillists']:
        conn.query('DELETE FROM ' + table)
    conn.insert('domain', domain='example.invalid')
    conn.insert('maillists', address='list@example.invalid')
    assert backend.is_domain_exists('example.invalid', conn=conn)
    assert not backend.is_domain_exists('absent.invalid', conn=conn)
    assert backend.is_maillist_exists('list@example.invalid', conn=conn)
    assert not backend.is_maillist_exists('absent@example.invalid', conn=conn)
    conn.ctx.db.close()

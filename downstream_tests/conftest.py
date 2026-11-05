"""Isolated settings and real connection factories; no production configuration."""
import importlib
import logging
import os
import runpy
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PROJECT = 'mlmmjadmin'
settings = types.ModuleType('settings')
settings.__dict__.update(runpy.run_path(str(ROOT / 'libs/default_settings.py')))
settings.backend = 'mysql'
settings.SQL_DB_DRIVER = 'pymysql'
settings.log_level = 'info'
settings.LOG_TARGET = 'stdout'
settings.iredmail_sql_db_type = 'mysql'
sys.modules['settings'] = settings

# Route application diagnostics to pytest rather than the host syslog socket.
log_module = types.ModuleType('libs.logger')
log_module.logger = logging.getLogger('socket-tests')
sys.modules['libs.logger'] = log_module

GROUPS = {
    'iRedAPD': ['vmail', 'amavisd', 'iredapd'],
    'iRedAdmin': ['vmail', 'iredadmin', 'amavisd', 'iredapd', 'fail2ban'],
    'mlmmjadmin': ['iredmail_sql'],
}[PROJECT]


def configure():
    settings.backend = 'mysql'
    settings.SQL_DB_DRIVER = 'pymysql'
    for name in GROUPS:
        for key, value in {
            'name': 'socket_test', 'user': 'socket_test',
            'password': 'isolated-test-password',
            'socket': os.environ.get('SOCKET_TEST_PATH', '/tmp/socket-test-missing.sock'),
            'server': '127.0.0.1', 'host': '127.0.0.1', 'port': '3306',
            'use_ssl': False,
        }.items():
            setattr(settings, name + '_db_' + key, value)


configure()
FACTORIES = []
if PROJECT == 'iRedAPD':
    import tools
    from libs import utils
    test_utils = importlib.import_module('tests.utils')
    for name in GROUPS:
        FACTORIES.extend([
            (name, 'engine', lambda n=name: utils.create_db_engine(n)),
            (name, 'tools', lambda n=name: tools.get_db_conn(n)),
            (name, 'test-helper', lambda n=name: test_utils.get_db_conn(n)),
        ])
elif PROJECT == 'iRedAdmin':
    from libs import iredutils
    from libs.sqllib import MYSQLWrap
    from tools import ira_tool_lib
    FACTORIES.append(('vmail', 'wrapper', lambda: MYSQLWrap.connect(None)))
    for name in GROUPS:
        FACTORIES.extend([
            (name, 'generic', lambda n=name: iredutils.get_db_conn(n, 'mysql')),
            (name, 'tools', lambda n=name: ira_tool_lib.get_db_conn(n)),
        ])
else:
    from backends.bk_iredmail_sql import MYSQLWrap
    FACTORIES.append(('iredmail_sql', 'wrapper', MYSQLWrap._MYSQLWrap__connect))
configure()


@pytest.fixture(autouse=True)
def clean_settings():
    configure()
    yield
    configure()


@pytest.fixture(params=FACTORIES, ids=[f'{n}-{kind}' for n, kind, _ in FACTORIES])
def factory(request):
    return request.param


@pytest.fixture
def live_database():
    if not os.environ.get('SOCKET_TEST_PATH'):
        pytest.skip('Set SOCKET_TEST_PATH using downstream_tests/run-mariadb.sh')


@pytest.fixture
def tmp_path():
    # macOS temporary-directory prefixes can exceed the Unix socket path limit.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='sql-test-', dir='/tmp') as directory:
        yield Path(directory)

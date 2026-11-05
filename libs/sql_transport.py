"""Explicit SQL transport selection without changing TCP defaults."""

import os


def mysql_socket(settings, db_name, dbn):
    """Return the configured socket only for a MySQL connection."""
    if dbn != 'mysql':
        return ''
    path = getattr(settings, db_name + '_db_socket', '')
    if path == '' or path is None:
        return ''
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError(db_name + '_db_socket must be an absolute socket path')
    return path


def web_transport(settings, db_name, dbn, host_suffix='server', with_ssl=False):
    """Build web.py transport arguments; TCP TLS options do not apply to sockets."""
    path = mysql_socket(settings, db_name, dbn)
    if path:
        return {'unix_socket': path}

    options = {
        'host': getattr(settings, db_name + '_db_' + host_suffix),
        'port': int(getattr(settings, db_name + '_db_port')),
    }
    if with_ssl:
        use_ssl = getattr(settings, db_name + '_db_use_ssl', False)
        if dbn == 'mysql':
            options['ssl'] = {'ssl': use_ssl}
        elif use_ssl:
            options['sslmode'] = 'prefer'
    return options


def describe_transport(settings, db_name, dbn, host_suffix='server'):
    """Describe the endpoint without reading credentials or unused TCP settings."""
    path = mysql_socket(settings, db_name, dbn)
    if path:
        return 'Unix socket ' + path
    return '{}:{}'.format(
        getattr(settings, db_name + '_db_' + host_suffix),
        getattr(settings, db_name + '_db_port'),
    )

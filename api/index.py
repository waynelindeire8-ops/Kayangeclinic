import sys
import os
import platform
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
_state = {'app': None}


def _text(start_response, body, status='200 OK'):
    start_response(status, [('Content-Type', 'text/plain; charset=utf-8')])
    return [body.encode('utf-8', 'replace')]


def _diag(step):
    out = []
    root = os.path.join(os.path.dirname(__file__), '..')
    if step == '0':
        out.append('python ' + sys.version)
        out.append('platform ' + platform.platform())
        out.append('files ' + ', '.join(sorted(os.listdir(root))[:60]))
        for k in ('VERCEL', 'NEON_DATABASE_URL', 'DATABASE_URL',
                  'SECRET_KEY', 'JWT_SECRET_KEY'):
            out.append('%s set=%s' % (k, bool(os.environ.get(k))))
        u = os.environ.get('NEON_DATABASE_URL') or ''
        out.append('neon host: ' + (u.split('@')[-1].split('/')[0] if u else '-'))
    elif step == '1':
        import flask, flask_jwt_extended, flask_cors
        out.append('flask libs ok')
        import psycopg2
        out.append('psycopg2 ' + psycopg2.__version__)
    elif step == '2':
        from app import create_app
        out.append('import app ok')
    elif step == '3':
        from app import create_app
        _state['app'] = create_app()
        out.append('create_app ok')
    elif step == '4':
        from app.backup import _get_pg_conn
        c = _get_pg_conn()
        cur = c.cursor()
        cur.execute('select 1')
        out.append('neon select 1: %s' % (cur.fetchone(),))
        c.close()
    return '\n'.join(out)


def _application(environ, start_response):
    path = environ.get('PATH_INFO', '')
    if path.startswith('/__diag-k7q2/'):
        try:
            return _text(start_response, _diag(path.rsplit('/', 1)[-1]))
        except BaseException:
            return _text(start_response, traceback.format_exc(),
                         '500 Internal Server Error')
    try:
        if _state['app'] is None:
            from app import create_app
            _state['app'] = create_app()
        return _state['app'](environ, start_response)
    except BaseException:
        return _text(start_response, traceback.format_exc(),
                     '500 Internal Server Error')


app = _application
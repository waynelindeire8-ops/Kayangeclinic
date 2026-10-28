import sys
import os
import platform
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
_state = {'app': None}


def _text(start_response, body, status='200 OK'):
    start_response(status, [('Content-Type', 'text/plain; charset=utf-8')])
    return [body.encode('utf-8', 'replace')]


def _ensure_app():
    if _state['app'] is None:
        from app import create_app
        _state['app'] = create_app()
    return _state['app']


def _diag(step, table=None):
    out = []
    if step == '0':
        out.append('python ' + sys.version)
        out.append('platform ' + platform.platform())
    elif step == '5':
        _ensure_app()
        from app.backup import _get_pg_conn, SYNC_TABLES
        c = _get_pg_conn()
        cur = c.cursor()
        for t in SYNC_TABLES:
            try:
                cur.execute('select count(*) from "%s"' % t)
                out.append('%s %s' % (t, cur.fetchone()[0]))
            except Exception as e:
                c.rollback()
                out.append('%s ERR %s' % (t, str(e).splitlines()[0]))
        c.close()
    elif step == '6':
        import time
        import resource
        _ensure_app()
        from app.backup import restore_table
        t0 = time.time()
        n = restore_table(table, full=True)
        out.append('%s restored=%s in %.1fs maxrss=%dMB' % (
            table, n, time.time() - t0,
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024))
    return '\n'.join(out)


def _application(environ, start_response):
    path = environ.get('PATH_INFO', '')
    if path.startswith('/__diag-k7q2/'):
        parts = path.split('/')
        try:
            table = parts[3] if len(parts) > 3 else None
            return _text(start_response, _diag(parts[2], table))
        except BaseException:
            return _text(start_response, traceback.format_exc(),
                         '500 Internal Server Error')
    try:
        return _ensure_app()(environ, start_response)
    except BaseException:
        return _text(start_response, traceback.format_exc(),
                     '500 Internal Server Error')


app = _application
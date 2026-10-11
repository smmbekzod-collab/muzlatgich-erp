"""Ephemeral real-Postgres race tests: guarded against production.

Creates a random TEST database through Django's test runner, and drops it when
the tests end. Never operates on staging business tables.
"""
import os
import uuid
import django

STAGING_ENV = "79dae0a2-be02-4dc2-ac16-3675ffc1aa62"

def main():
    if (os.environ.get("RAILWAY_ENVIRONMENT_ID") != STAGING_ENV
            or os.environ.get("ALLOW_ISOLATED_POSTGRES_TEST") != "yes"):
        raise SystemExit("REFUSED: explicitly approved Railway STAGING only.")
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
    django.setup()
    from django.conf import settings
    from django.db import connection
    from django.core.management import call_command
    if connection.vendor != 'postgresql':
        raise SystemExit('REFUSED: PostgreSQL is required.')
    # Use an unpredictable, unique DB; never drop/reuse an existing DB.
    suffix=uuid.uuid4().hex[:16]
    temporary=f'erp_race_{suffix}'
    with connection.cursor() as cur:
        cur.execute('SELECT 1 FROM pg_database WHERE datname=%s',(temporary,))
        if cur.fetchone():
            raise SystemExit('REFUSED: target test DB already exists')
        cur.execute('SELECT current_database()')
        current=cur.fetchone()[0]
    if current != 'railway':
        raise SystemExit('REFUSED: unexpected STAGING source database name')
    settings.DATABASES['default']['TEST']={'NAME':temporary}
    print(f'ISOLATED STAGING PostgreSQL TEST DB {temporary}; source={current}; '
          f'expected automatic cleanup after test',flush=True)
    call_command('test','warehouse.test_concurrency_postgres',verbosity=2,interactive=False)

if __name__=='__main__':
    main()

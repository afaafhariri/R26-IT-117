-- Creates the gateway's own login and database. Safe to run more than once:
-- anything that already exists is left alone.
--
-- Run it as a superuser, passing the password to give the gateway login:
--   psql -U postgres -v gateway_password='...' -f gateway/db/create_authdb.sql
-- For the docker-compose Postgres, see "Docker" in gateway/README.md.
--
-- The tables themselves are created by the migrations (alembic upgrade head).

\set ON_ERROR_STOP on

SELECT format('CREATE ROLE gateway LOGIN PASSWORD %L', :'gateway_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gateway') \gexec

SELECT 'CREATE DATABASE authdb OWNER gateway'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'authdb') \gexec

REVOKE ALL ON DATABASE authdb FROM PUBLIC;

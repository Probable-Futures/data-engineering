create database probable_futures encoding UTF8;

create extension if not exists plpgsql with schema pg_catalog;
create extension if not exists "uuid-ossp" with schema public;
create extension if not exists citext with schema public;
create extension if not exists pgcrypto with schema public;
create extension if not exists pg_stat_statements with schema public;
create extension if not exists postgis;
--needed for postgis_tiger_geocoder
create extension if not exists fuzzystrmatch;
create extension if not exists postgis_tiger_geocoder;
create extension if not exists postgis_topology;
-- useful for spatial indexes
create extension if not exists btree_gist;

--! split: 0020-schemas.sql
/*
 * Read about graphile schemas here:
 * https://www.graphile.org/postgraphile/namespaces/#advice
 */
drop schema if exists pf_public cascade;
drop schema if exists pf_hidden cascade;
drop schema if exists pf_private cascade;

create schema pf_public;
comment on schema pf_public is
  E'Namespace for tables and functions exposed to GraphQL';

create schema pf_hidden;
comment on schema pf_hidden is
  E'Namespace for implementation details of the `pf_public` schema that are not intended to be exposed publicly';

create schema pf_private;
comment on schema pf_private is
  E'Namespace for private tables and functions that should not be publicly accessible. Users need a `SECURITY DEFINER` function that selectively grants access to the namespace';

/*
 * This trigger is used on tables with created_at and updated_at to ensure that
 * these timestamps are kept valid (namely: `created_at` cannot be changed, and
 * `updated_at` must be monotonically increasing).
 */
create function pf_private.tg__timestamps() returns trigger as $$
begin
  NEW.created_at = (case when TG_OP = 'INSERT' then NOW() else OLD.created_at end);
  NEW.updated_at = (case when TG_OP = 'UPDATE' and OLD.updated_at >= NOW() then OLD.updated_at + interval '1 millisecond' else NOW() end);
  return NEW;
end;
$$ language plpgsql volatile;
comment on function pf_private.tg__timestamps() is
  E'This trigger should be called on all tables with created_at, updated_at - it ensures that they cannot be manipulated and that updated_at will always be larger than the previous updated_at.';


-- Store valid dataset models as a table
-- https://stackoverflow.com/a/41655273
create table if not exists pf_public.pf_dataset_model_sources (
  model text primary key
);

comment on table pf_public.pf_dataset_model_sources is
  E'Table for referencing valid climate dataset model source names';

insert into pf_public.pf_dataset_model_sources (model) values
  ('GCM, CMIP5'),
  ('RCM, global REMO'),
  ('RCM, regional REMO');

create table if not exists pf_public.pf_dataset_units (
  unit citext primary key,
  unit_long text
);
comment on table pf_public.pf_dataset_units is
  E'Table for referencing valid climate dataset unit types';

insert into pf_public.pf_dataset_units (unit, unit_long) values
  ('days', 'Number of days'),
  ('temperature (°C)', null),
  ('class', null);

create table if not exists pf_public.pf_dataset_categories (
  category citext primary key
);
comment on table pf_public.pf_dataset_categories is
  E'Table for referencing valid climate dataset category names';

insert into pf_public.pf_dataset_categories (category) values
  ('basics'),
  ('increasing heat'),
  ('decreasing cold'),
  ('heat and humidity');

create table if not exists pf_public.pf_datasets (
  -- use internal id as primary key
  id integer unique primary key,
  slug citext not null unique,
  name text not null,
  description text,
  resolution text,
  category citext references pf_public.pf_dataset_categories(category) on update cascade,
  model text references pf_public.pf_dataset_model_sources(model) on update cascade,
  unit citext references pf_public.pf_dataset_units(unit) on update cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index pf_dataset_slug_idx on pf_public.pf_datasets (slug);
create index pf_dataset_category_idx on pf_public.pf_datasets (category);
create index pf_dataset_model_idx on pf_public.pf_datasets (model);
create index pf_dataset_unit_idx on pf_public.pf_datasets (unit);

create trigger _100_timestamps
  before insert or update on pf_public.pf_datasets
  for each row
  execute procedure pf_private.tg__timestamps();


create table if not exists pf_public.pf_statistical_variable_names (
  slug citext primary key,
  name text,
  dataset_id integer references pf_public.pf_datasets(id) on update cascade,
  description text
);

comment on table pf_public.pf_statistical_variable_names is
  E'Table storing variable names across datasets';

create table if not exists pf_public.pf_statistical_variable_methods (
  slug citext primary key,
  name text,
  description text
);

comment on table pf_public.pf_statistical_variable_methods is
  E'Table storing variable categories, e.g. mean, 90th';

create table if not exists pf_public.pf_dataset_coordinates (
  id uuid default gen_random_uuid() primary key,
  point geography(Point,4326),
  md5_hash text unique generated always as (md5(ST_AsEWKT(point))) stored,
  model text references pf_public.pf_dataset_model_sources(model) on update cascade,
  cell geography(Polygon, 4326) generated always as (
    ST_MakeEnvelope(
      ((ST_X(point::geometry)) - 0.09999999660721),
      ((ST_Y(point::geometry))  + 0.099999999999991),
      ((ST_X(point::geometry)) + 0.09999999660721),
      ((ST_Y(point::geometry))  - 0.099999999999991),
    4326)::geography) stored,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table pf_public.pf_dataset_coordinates is
  E'Table storing coordinates used in PF Climate Datasets';

comment on column pf_public.pf_dataset_coordinates.md5_hash is
  E'MD5 Hash of the EWKT of the coordinate point, used as a FK for raw and statistical data'

comment on column pf_public.pf_dataset_coordinates.cell is
  E'Bounding box around the climate point, used for dataset tilesets'

create index pf_dataset_coordinate_point_idx on pf_public.pf_dataset_coordinates using gist (point);
create index pf_dataset_coordinate_point_hash_idx on pf_public.pf_dataset_coordinates (md5_hash);
create index pf_dataset_coordinate_model_idx on pf_public.pf_dataset_coordinates (model);

create trigger _100_timestamps before insert or update on pf_public.pf_dataset_coordinates
  for each row
  execute procedure pf_private.tg__timestamps();

create table if not exists pf_public.pf_warming_scenarios (
  slug citext primary key,
  name text,
  description text
);

create table if not exists pf_public.pf_dataset_statistics (
  id uuid default gen_random_uuid() primary key,
  dataset_id integer not null references pf_public.pf_datasets(id) on update cascade,
  coordinate_hash text references pf_public.pf_dataset_coordinates(md5_hash) on update cascade,
  warming_scenario citext references pf_public.pf_warming_scenarios(slug) on update cascade,
  variable_method citext references pf_public.pf_statistical_variable_methods(slug) on update cascade,
  variable_name citext references pf_public.pf_statistical_variable_names(slug) on update cascade,
  variable_value numeric(4,1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table pf_public.pf_dataset_statistics is
  E'Table storing statistical data (mean, percentile, etc) for PF Climate Datasets';


create index pf_dataset_stats_dataset_idx on pf_public.pf_dataset_statistics (dataset_id);
create index pf_dataset_stats_coordinate_idx on pf_public.pf_dataset_statistics (coordinate_hash);
create index pf_dataset_stats_warming_idx on pf_public.pf_dataset_statistics (warming_scenario);
-- create index pf_dataset_stats_method_idx on pf_public.pf_dataset_statistics (variable_method);

create trigger _100_timestamps before insert or update on pf_public.pf_dataset_statistics
  for each row
  execute procedure pf_private.tg__timestamps();

create table if not exists pf_public.pf_dataset_data (
  id uuid default gen_random_uuid() primary key,
  dataset_id integer not null references pf_public.pf_datasets(id) on update cascade,
  coordinate_hash text references pf_public.pf_dataset_coordinates(md5_hash) on update cascade,
  warming_scenario citext references pf_public.pf_warming_scenarios(slug) on update cascade,
  data_values numeric(4,1)[3][21] not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table pf_public.pf_dataset_data is
  E'Table storing raw data values for PF Climate Datasets';

create index pf_data_dataset_idx on pf_public.pf_dataset_data (dataset_id);
create index pf_data_coordinate_idx on pf_public.pf_dataset_data (coordinate_hash);
create index pf_data_warming_idx on pf_public.pf_dataset_statistics (warming_scenario);

create trigger _100_timestamps before insert or update on pf_public.pf_dataset_data
  for each row
  execute procedure pf_private.tg__timestamps();

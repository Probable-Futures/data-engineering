create database probable_futures encoding UTF8;

--------------------------------------------------------------------------------
-- Extensions
--------------------------------------------------------------------------------
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

--------------------------------------------------------------------------------
-- Schemas
--------------------------------------------------------------------------------
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

--------------------------------------------------------------------------------
-- Shared Functions
--------------------------------------------------------------------------------
/*
 * This trigger is used on tables with created_at and updated_at to ensure that
 * these timestamps are kept valid (namely: `created_at` cannot be changed, and
 * `updated_at` must be monotonically increasing).
 */
create or replace function pf_private.tg__timestamps() returns trigger as $$
begin
  NEW.created_at = (case when TG_OP = 'INSERT' then NOW() else OLD.created_at end);
  NEW.updated_at = (case when TG_OP = 'UPDATE' and OLD.updated_at >= NOW() then OLD.updated_at + interval '1 millisecond' else NOW() end);
  return NEW;
end;
$$ language plpgsql volatile;
comment on function pf_private.tg__timestamps() is
  E'This trigger should be called on all tables with created_at, updated_at - it ensures that they cannot be manipulated and that updated_at will always be larger than the previous updated_at.';

/*
 * This trigger ensures that a `coordinate_id` column is in sync with a `coordinate_hash` column.
 * The `coordinate_id` column is to improve join performance on large tables.
 */
create or replace function pf_private.set_coordinate_id_from_hash()
  returns trigger as $$
begin
  NEW.coordinate_id = (
      case when TG_OP = 'INSERT'
           then (select id from pf_public.pf_dataset_coordinates
                  where md5_hash = NEW.coordinate_hash)
           when TG_OP = 'UPDATE' and
                  OLD.coordinate_hash is distinct from NEW.coordinate_hash
           then (select id from pf_public.pf_dataset_coordinates
                  where md5_hash = NEW.coordinate_hash)
           else OLD.coordinate_id
      end
      );
  return NEW;
end;
$$ language plpgsql volatile;
comment on function pf_private.set_coordinate_id_from_hash() is
        E'Trigger function to set coordinate_id on rows with coordinate hashes';

--------------------------------------------------------------------------------
-- Dataset Model Sources
--------------------------------------------------------------------------------
create table if not exists pf_public.pf_dataset_model_sources (
  model text primary key
);
comment on table pf_public.pf_dataset_model_sources is
  E'Table for referencing valid climate dataset model source names';

insert into pf_public.pf_dataset_model_sources (model) values
  ('GCM, CMIP5'),
  ('RCM, global REMO'),
  ('RCM, regional REMO'),
  ('RCM, global RegCM and REMO');

--------------------------------------------------------------------------------
-- Dataset Units
--------------------------------------------------------------------------------
create table if not exists pf_public.pf_dataset_units (
  unit citext primary key,
  unit_long text
);
comment on table pf_public.pf_dataset_units is
  E'Table for referencing valid climate dataset unit types';

insert into pf_public.pf_dataset_units (unit, unit_long) values
  ('days', 'number of days'),
  ('°C', 'temperature (°C)'),
  ('cm', 'centimeters'),
  ('class', null);

--------------------------------------------------------------------------------
-- Dataset Categories
--------------------------------------------------------------------------------
create table if not exists pf_public.pf_dataset_categories (
  category citext primary key
);
comment on table pf_public.pf_dataset_categories is
  E'Table for referencing valid climate dataset category names';

insert into pf_public.pf_dataset_categories (category) values
  ('increasing heat'),
  ('decreasing cold'),
  ('heat and humidity'),
  ('precipitation');

--------------------------------------------------------------------------------
-- Datasets
--------------------------------------------------------------------------------
create table if not exists pf_public.pf_datasets (
  -- use internal id as primary key
  id integer unique primary key,
  slug citext not null unique,
  name text not null,
  description text,
  resolution text,
  category citext references pf_public.pf_dataset_categories(category)
    on update cascade,
  model text references pf_public.pf_dataset_model_sources(model)
    on update cascade,
  unit citext references pf_public.pf_dataset_units(unit)
    on update cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index pf_dataset_slug_idx
  on pf_public.pf_datasets (slug);

create index pf_dataset_category_idx
  on pf_public.pf_datasets (category);

create index pf_dataset_model_idx
  on pf_public.pf_datasets (model);

create index pf_dataset_unit_idx
  on pf_public.pf_datasets (unit);

drop trigger if exists _100_timestamps
  on pf_public.pf_datasets cascade;
create trigger _100_timestamps
  before insert or update on pf_public.pf_datasets
  for each row
  execute procedure pf_private.tg__timestamps();

--------------------------------------------------------------------------------
-- Statistical Variable Names
--------------------------------------------------------------------------------
create table if not exists pf_public.pf_statistical_variable_names (
  slug citext primary key,
  name text,
  dataset_id integer references pf_public.pf_datasets(id)
    on update cascade
    on delete cascade,
  description text
);
comment on table pf_public.pf_statistical_variable_names is
  E'Table storing variable names across datasets';

--------------------------------------------------------------------------------
-- Statistical Variable Methods
-- (do we still need these?)
--------------------------------------------------------------------------------
create table if not exists pf_public.pf_statistical_variable_methods (
  slug citext primary key,
  name text,
  description text
);
comment on table pf_public.pf_statistical_variable_methods is
  E'Table storing variable categories, e.g. mean, 90th';

insert into pf_public.pf_statistical_variable_methods (slug, name) values
  ('pct90', '90th percentile'),
  ('pct10', '10th percentile'),
  ('mean', 'mean');

comment on table pf_public.pf_statistical_variable_methods is
  E'Table storing variable categories, e.g. mean, 90th';


drop table if exists pf_public.pf_dataset_model_grids;
create table if not exists pf_public.pf_dataset_model_grids (
  grid text primary key,
  resolution text unique -- we could parse these further if needed
);

insert into pf_public.pf_dataset_model_grids (grid, resolution) values
  ('GCM', '240,120&167,167'),
  ('RCM', '1800,901&22,22');


drop table if exists pf_public.pf_dataset_model_sources cascade;
create table if not exists pf_public.pf_dataset_model_sources (
  model text primary key,
  grid text not null references pf_public.pf_dataset_model_grids(grid)
);

insert into pf_public.pf_dataset_model_sources (model, grid) values
  ('CMIP5', 'GCM'),
  ('global REMO', 'RCM'),
  ('regional REMO', 'RCM'),
  ('global RegCM and REMO', 'RCM');

--------------------------------------------------------------------------------
-- Dataset Coordinates
--------------------------------------------------------------------------------
create table if not exists pf_public.pf_dataset_coordinates (
  id uuid default gen_random_uuid() primary key,
  md5_hash text unique generated always as (
    md5(grid || ST_AsEWKT(point))) stored,
  grid text references pf_public.pf_dataset_model_grids(grid)
    on update cascade,
  point geography(Point,4326) not null,
  cell geography(Polygon, 4326) generated always as (
    -- RCM and GCM datasets have different grids
    case
      when grid = 'RCM' then ST_MakeEnvelope(
          ((ST_X(point::geometry)) - 0.09999999660721),
          ((ST_Y(point::geometry)) + 0.099999999999991),
          ((ST_X(point::geometry)) + 0.09999999660721),
          ((ST_Y(point::geometry)) - 0.099999999999991),
        4326)::geography
      when grid = 'GCM' then ST_MakeEnvelope(
          ((ST_X(point::geometry)) - 0.625),
          ((ST_Y(point::geometry)) + 0.471204188481675),
          ((ST_X(point::geometry)) + 0.625),
          ((ST_Y(point::geometry)) - 0.471204188481675),
        4326)::geography
    end) stored,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table pf_public.pf_dataset_coordinates is
  E'Table storing coordinates used in PF Climate Datasets';
comment on column pf_public.pf_dataset_coordinates.md5_hash is
  E'MD5 Hash of the EWKT of the coordinate point, used as a FK for raw and statistical data';
comment on column pf_public.pf_dataset_coordinates.cell is
  E'Bounding box around the climate point, used for dataset tilesets';

create index pf_dataset_coordinate_point_idx
  on pf_public.pf_dataset_coordinates
  using gist (point);

create index pf_dataset_coordinate_point_hash_idx
  on pf_public.pf_dataset_coordinates
  using hash (md5_hash);

create index pf_dataset_coordinate_grid_idx
  on pf_public.pf_dataset_coordinates (grid);

drop trigger if exists _100_timestamps
  on pf_public.pf_dataset_coordinates cascade;
create trigger _100_timestamps
  before insert or update on pf_public.pf_dataset_coordinates
  for each row
  execute procedure pf_private.tg__timestamps();

--------------------------------------------------------------------------------
-- Warming Scenarios
--------------------------------------------------------------------------------
create table if not exists pf_public.pf_warming_scenarios (
  slug citext primary key,
  name text,
  description text
);

insert into pf_public.pf_warming_scenarios (slug) values
  ('0.5'),
  ('1.0'),
  ('1.5'),
  ('2.0'),
  ('2.5'),
  ('3.0');

--------------------------------------------------------------------------------
-- Dataset Statistics
--------------------------------------------------------------------------------
create table pf_public.pf_dataset_statistics (
  id uuid default gen_random_uuid() primary key,
  dataset_id integer not null references pf_public.pf_datasets(id)
    on update cascade
    on delete cascade,
  coordinate_id uuid references pf_public.pf_dataset_coordinates(id)
    on update cascade,
  coordinate_hash text references pf_public.pf_dataset_coordinates(md5_hash)
    on update cascade,
  warming_scenario citext references pf_public.pf_warming_scenarios(slug)
    on update cascade,
  pctl10 numeric(5,1),
  mean numeric(5,1),
  pctl90 numeric(5,1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table pf_public.pf_dataset_statistics is
  E'Table storing statistical data (mean, percentile, etc) for PF Climate Datasets';

create index pf_dataset_stats_dataset_idx
  on pf_public.pf_dataset_statistics (dataset_id);

create index pf_dataset_stats_coordinate_hash_idx
  on pf_public.pf_dataset_statistics
  using hash(coordinate_hash);

create index pf_dataset_stats_coordinate_idx
  on pf_public.pf_dataset_statistics (coordinate_id);

create index pf_dataset_stats_warming_idx
  on pf_public.pf_dataset_statistics (warming_scenario);

drop trigger if exists _100_timestamps
  on pf_public.pf_dataset_statistics cascade;
create trigger _100_timestamps
  before insert or update on pf_public.pf_dataset_statistics
  for each row
  execute procedure pf_private.tg__timestamps();

drop trigger if exists _200_set_coordinate_id
  on pf_public.pf_dataset_statistics cascade;
create trigger _200_set_coordinate_id
  before insert or update on pf_public.pf_dataset_statistics
  for each row
  execute procedure pf_private.set_coordinate_id_from_hash();
comment on trigger _200_set_coordinate_id
  on pf_public.pf_dataset_statistics is
  E'Set coordinate_id for improved join performance';

create or replace view pf_private.aggregate_pf_dataset_statistics as
  select coordinate_id, dataset_id,
    unnest(array_agg(pctl10) filter (where warming_scenario = '0.5')) as data_baseline_pctl10,
    unnest(array_agg(mean) filter (where warming_scenario = '0.5')) as data_baseline_mean,
    unnest(array_agg(pctl90) filter (where warming_scenario = '0.5')) as data_baseline_pctl90,
    unnest(array_agg(pctl10) filter (where warming_scenario = '1.0')) as data_1c_pctl10,
    unnest(array_agg(mean) filter (where warming_scenario = '1.0')) as data_1c_mean,
    unnest(array_agg(pctl90) filter (where warming_scenario = '1.0')) as data_1c_pctl90,
    unnest(array_agg(pctl10) filter (where warming_scenario = '1.5')) as data_1_5c_pctl10,
    unnest(array_agg(mean) filter (where warming_scenario = '1.5')) as data_1_5c_mean,
    unnest(array_agg(pctl90) filter (where warming_scenario = '1.5')) as data_1_5c_pctl90,
    unnest(array_agg(pctl10) filter (where warming_scenario = '2.0')) as data_2c_pctl10,
    unnest(array_agg(mean) filter (where warming_scenario = '2.0')) as data_2c_mean,
    unnest(array_agg(pctl90) filter (where warming_scenario = '2.0')) as data_2c_pctl90,
    unnest(array_agg(pctl10) filter (where warming_scenario = '2.5')) as data_2_5c_pctl10,
    unnest(array_agg(mean) filter (where warming_scenario = '2.5')) as data_2_5c_mean,
    unnest(array_agg(pctl90) filter (where warming_scenario = '2.5')) as data_2_5c_pctl90,
    unnest(array_agg(pctl10) filter (where warming_scenario = '3.0')) as data_3c_pctl10,
    unnest(array_agg(mean) filter (where warming_scenario = '3.0')) as data_3c_mean,
    unnest(array_agg(pctl90) filter (where warming_scenario = '3.0')) as data_3c_pctl90
  from pf_public.pf_dataset_statistics
  group by coordinate_id, dataset_id;
comment on view pf_private.aggregate_pf_dataset_statistics is
  E'View of aggregate dataset statistics across all warming scenarios';

create or replace view pf_private.aggregate_pf_dataset_statistic_cells as
  select coords.cell, stats.*
  from pf_private.aggregate_pf_dataset_statistics stats
  join pf_public.pf_dataset_coordinates coords
  on stats.coordinate_id = coords.id;
comment on view pf_private.aggregate_pf_dataset_statistic_cells is
  E'View of aggregate dataset statistics joined with coordinate cells';

--------------------------------------------------------------------------------
-- Dataset Data
--------------------------------------------------------------------------------
create table if not exists pf_public.pf_dataset_data (
  id uuid default gen_random_uuid() primary key,
  dataset_id integer not null references pf_public.pf_datasets(id)
    on update cascade,
  coordinate_id uuid references pf_public.pf_dataset_coordinates(id)
    on update cascade,
  coordinate_hash text references pf_public.pf_dataset_coordinates(md5_hash)
    on update cascade,
  warming_scenario citext references pf_public.pf_warming_scenarios(slug)
    on update cascade,
  data_values numeric(4,1)[3][21] not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table pf_public.pf_dataset_data is
  E'Table storing raw data values for PF Climate Datasets';

create index pf_data_dataset_idx
  on pf_public.pf_dataset_data (dataset_id);

create index pf_data_coordinate_hash_idx
  on pf_public.pf_dataset_data
  using hash(coordinate_hash);

create index pf_data_coordinate_idx
  on pf_public.pf_dataset_data (coordinate_id);

create index pf_data_warming_idx
  on pf_public.pf_dataset_statistics (warming_scenario);

drop trigger if exists _100_timestamps
  on pf_public.pf_dataset_data cascade;
create trigger _100_timestamps before insert or update on pf_public.pf_dataset_data
  for each row
  execute procedure pf_private.tg__timestamps();

drop trigger if exists _200_set_coordinate_id
  on pf_public.pf_dataset_data cascade;
create trigger _200_set_coordinate_id
  before insert or update on pf_public.pf_dataset_data
  for each row
  execute procedure pf_private.set_coordinate_id_from_hash();
comment on trigger _200_set_coordinate_id
  on pf_public.pf_dataset_data is
  E'Set coordinate_id for improved join performance';

-- pgFormatter-ignore

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
  ('days', 'Number of days per year'),
  ('°C', 'Temperature (°C)'),
  ('cm', 'Change in annual precipitation (cm)'),
  ('mm', 'Change in precipitation (mm)'),
  ('x as frequent', 'Times more/less frequent'),
  ('%', 'Annual likelihood (%)'),
  ('z-score', 'Z-score'),
  ('class', 'Climate zones');

--------------------------------------------------------------------------------
-- Dataset Categories
--------------------------------------------------------------------------------
create table if not exists pf_public.pf_dataset_parent_categories (name text primary key, label text);

create table if not exists pf_public.pf_dataset_sub_categories (
  name text primary key,
  parent_category citext not null,
  unique (name, parent_category),
  constraint pf_dataset_sub_categories_parent_category_fkey foreign key (parent_category) references pf_public.pf_dataset_parent_categories(name)
);

insert into
  pf_public.pf_dataset_parent_categories (name, label)
values
  ('heat', 'heat'),
  ('water', 'precipitation'),
  ('drought', 'soil'),
  ('other', 'Other maps');

insert into
  pf_public.pf_dataset_sub_categories (name, parent_category)
values
  ('increasing heat', 'heat'),
  ('decreasing cold', 'heat'),
  ('heat and humidity', 'heat');

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
  parent_category text references pf_public.pf_dataset_parent_categories(name) on update cascade,
  sub_category text references pf_public.pf_dataset_sub_categories(name) on update cascade,
  model text references pf_public.pf_dataset_model_sources(model)
    on update cascade,
  unit citext references pf_public.pf_dataset_units(unit)
    on update cascade,
  min_value integer DEFAULT 0,
  max_value integer DEFAULT 0,
  data_variables text[] DEFAULT '{"10th percentile",average,"90th percentile"}'::text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index pf_dataset_slug_idx
  on pf_public.pf_datasets (slug);

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
create table if not exists pf_public.pf_grid_coordinates (
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
          ((ST_X(point::geometry)) - 0.75225225),
          ((ST_Y(point::geometry)) + 0.75225225),
          ((ST_X(point::geometry)) + 0.75225225),
          ((ST_Y(point::geometry)) - 0.75225225),
        4326)::geography
    end) stored,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table pf_public.pf_grid_coordinates is
  E'Table storing coordinates used in PF Climate Datasets';
comment on column pf_public.pf_grid_coordinates.md5_hash is
  E'MD5 Hash of the EWKT of the coordinate point, used as a FK for raw and statistical data';
comment on column pf_public.pf_grid_coordinates.cell is
  E'Bounding box around the climate point, used for dataset tilesets';

create index pf_dataset_coordinate_point_idx
  on pf_public.pf_grid_coordinates
  using gist (point);

create index pf_dataset_coordinate_point_hash_idx
  on pf_public.pf_grid_coordinates
  using hash (md5_hash);

create index pf_dataset_coordinate_grid_idx
  on pf_public.pf_grid_coordinates (grid);

drop trigger if exists _100_timestamps
  on pf_public.pf_grid_coordinates cascade;
create trigger _100_timestamps
  before insert or update on pf_public.pf_grid_coordinates
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
  coordinate_hash text references pf_public.pf_grid_coordinates(md5_hash)
    on update cascade,
  warming_scenario citext references pf_public.pf_warming_scenarios(slug)
    on update cascade,
  low_value numeric(6,1),
  mid_value numeric(6,1),
  high_value numeric(6,1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  values numeric[],
  cumulative_probability numeric[]
);
comment on table pf_public.pf_dataset_statistics is
  E'Table storing statistical data (mean, percentile, etc) for PF Climate Datasets';

create index pf_dataset_stats_dataset_idx
  on pf_public.pf_dataset_statistics (dataset_id);

create index pf_dataset_stats_coordinate_hash_idx
  on pf_public.pf_dataset_statistics
  using hash(coordinate_hash);

create index pf_dataset_stats_warming_idx
  on pf_public.pf_dataset_statistics (warming_scenario);

drop trigger if exists _100_timestamps
  on pf_public.pf_dataset_statistics cascade;
create trigger _100_timestamps
  before insert or update on pf_public.pf_dataset_statistics
  for each row
  execute procedure pf_private.tg__timestamps();

create or replace view pf_private.aggregate_pf_dataset_statistics as
  select coordinate_hash, dataset_id,
    unnest(array_agg(low_value) filter (where warming_scenario = '0.5')) as data_baseline_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '0.5')) as data_baseline_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '0.5')) as data_baseline_high,
    unnest(array_agg(low_value) filter (where warming_scenario = '1.0')) as data_1c_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '1.0')) as data_1c_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '1.0')) as data_1c_high,
    unnest(array_agg(low_value) filter (where warming_scenario = '1.5')) as data_1_5c_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '1.5')) as data_1_5c_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '1.5')) as data_1_5c_high,
    unnest(array_agg(low_value) filter (where warming_scenario = '2.0')) as data_2c_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '2.0')) as data_2c_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '2.0')) as data_2c_high,
    unnest(array_agg(low_value) filter (where warming_scenario = '2.5')) as data_2_5c_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '2.5')) as data_2_5c_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '2.5')) as data_2_5c_high,
    unnest(array_agg(low_value) filter (where warming_scenario = '3.0')) as data_3c_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '3.0')) as data_3c_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '3.0')) as data_3c_high
  from pf_public.pf_dataset_statistics
  group by coordinate_hash, dataset_id;
comment on view pf_private.aggregate_pf_dataset_statistics is
  E'View of aggregate dataset statistics across all warming scenarios';

create or replace view pf_private.aggregate_pf_dataset_statistic_cells as
  select coords.cell, stats.*
  from pf_private.aggregate_pf_dataset_statistics stats
  join pf_public.pf_grid_coordinates coords
  on stats.coordinate_hash = coords.md5_hash;
comment on view pf_private.aggregate_pf_dataset_statistic_cells is
  E'View of aggregate dataset statistics joined with coordinate cells';

create or replace view pf_private.aggregate_pf_dataset_statistics_with_percentage as
select
  t.*,
  case when data_1c_mid = - 99999 then
    data_1c_mid
  else
    round((data_1c_mid / data_baseline_mid) * 100)
  end as data_1c_mid_percent,
  case when data_1_5c_mid = - 99999 then
    data_1_5c_mid
  else
    round((data_1_5c_mid / data_baseline_mid) * 100)
  end as data_1_5c_mid_percent,
  case when data_2c_mid = - 99999 then
    data_2c_mid
  else
    round((data_2c_mid / data_baseline_mid) * 100)
  end as data_2c_mid_percent,
  case when data_2_5c_mid = - 99999 then
    data_2_5c_mid
  else
    round((data_2_5c_mid / data_baseline_mid) * 100)
  end as data_2_5c_mid_percent,
  case when data_3c_mid = - 99999 then
    data_3c_mid
  else
    round((data_3c_mid / data_baseline_mid) * 100)
  end as data_3c_mid_percent
from (
  select
    coordinate_hash,
    dataset_id,
    unnest(array_agg(low_value) filter (where warming_scenario = '0.5')) as data_baseline_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '0.5')) as data_baseline_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '0.5')) as data_baseline_high,
    unnest(array_agg(low_value) filter (where warming_scenario = '1.0')) as data_1c_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '1.0')) as data_1c_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '1.0')) as data_1c_high,
    unnest(array_agg(low_value) filter (where warming_scenario = '1.5')) as data_1_5c_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '1.5')) as data_1_5c_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '1.5')) as data_1_5c_high,
    unnest(array_agg(low_value) filter (where warming_scenario = '2.0')) as data_2c_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '2.0')) as data_2c_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '2.0')) as data_2c_high,
    unnest(array_agg(low_value) filter (where warming_scenario = '2.5')) as data_2_5c_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '2.5')) as data_2_5c_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '2.5')) as data_2_5c_high,
    unnest(array_agg(low_value) filter (where warming_scenario = '3.0')) as data_3c_low,
    unnest(array_agg(mid_value) filter (where warming_scenario = '3.0')) as data_3c_mid,
    unnest(array_agg(high_value) filter (where warming_scenario = '3.0')) as data_3c_high
  from
    pf_public.pf_dataset_statistics
  group by
    coordinate_hash,
    dataset_id) t;

comment on view pf_private.aggregate_pf_dataset_statistics_with_percentage is E'View of aggregate dataset statistics across all warming scenarios';

create or replace view pf_private.aggregate_pf_dataset_statistic_cells_with_percentage as
select
  coords.cell,
  stats.*
from
  pf_private.aggregate_pf_dataset_statistics_with_percentage stats
  join pf_public.pf_grid_coordinates coords on stats.coordinate_hash = coords.md5_hash;

comment on view pf_private.aggregate_pf_dataset_statistic_cells_with_percentage is E'View of aggregate dataset statistics joined with coordinate cells';

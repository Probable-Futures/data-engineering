-- drop role if exists pf_owner;
-- create role pf_owner with login password 'password' SUPERUSER;
-- comment on role pf_owner is
--   E'Role that `owns` the database and is used for migrations and the worker.';

-- --
-- -- Create database
-- create database probable_futures OWNER pf_owner
--   ENCODING UTF8;

-- comment on database probable_futures is
--   E'Primary database for the Probable Futures core platform';

-- Database permissions
revoke all on database probable_futures from public;
grant all on database probable_futures to pf_owner;

create extension if not exists plpgsql with schema pg_catalog;

create extension if not exists "uuid-ossp" with schema public;

create extension if not exists citext with schema public;

create extension if not exists pgcrypto with schema public;

create extension if not exists pg_stat_statements with schema public;

create extension if not exists postgis;

--needed for postgis_tiger_geocoder
create extension if not exists fuzzystrmatch;

--optional used by postgis_tiger_geocoder, or can be used standalone
-- create extension if not exists address_standardizer;

-- create extension if not exists address_standardizer_data_us;

create extension if not exists postgis_tiger_geocoder;

create extension if not exists postgis_topology;

-- useful for spatial indexes
create extension if not exists btree_gist;

--! Previous: -
--! Hash: sha1:bdeb7e5c3fab50162779f6474c0ccefb845c6118

--! split: 0001-reset.sql
/*
 * Graphile Migrate will run our `current/...` migrations in one batch. Since
 * this is our first migration it's defining the entire database, so we first
 * drop anything that may have previously been created
 * (app_public/app_hidden/app_private) so that we can start from scratch.
 */

drop role if exists pf_graphile;
create role pf_graphile with login password 'password' noinherit;
comment on role pf_graphile is
  E'Role with minimal permissions used for connections from the postgraphile server.';

grant connect on database probable_futures to pf_graphile;

-- Role for un-authenticated queries
drop role  if exists pf_visitor;
create role pf_visitor;
comment on role pf_visitor is
  E'Role used for executing database queries from unauthenticated server requests.';

-- Role for queries from an authenticated user
drop role if exists pf_authenticated;
create role pf_authenticated;
comment on role pf_authenticated is
  E'Role used for executing database queries from authenticated server requests.';

grant pf_visitor TO pf_graphile;
grant pf_authenticated TO pf_graphile;

drop schema if exists pf_public cascade;
drop schema if exists pf_hidden cascade;
drop schema if exists pf_private cascade;

--! split: 0010-public-permissions.sql
/*
 * The `public` *schema* contains things like PostgreSQL extensions. We
 * deliberately do not install application logic into the public schema
 * (instead storing it to app_public/app_hidden/app_private as appropriate),
 * but none the less we don't want untrusted roles to be able to install or
 * modify things into the public schema.
 *
 * The `public` *role* is automatically inherited by all other roles; we only
 * want specific roles to be able to access our database so we must revoke
 * access to the `public` role.
 */

revoke all on schema public from public;

alter default privileges revoke all on sequences from public;
alter default privileges revoke all on functions from public;

-- Of course we want our database owner to be able to do anything inside the
-- database, so we grant access to the `public` schema
grant all on schema public to pf_owner;

--! split: 0020-schemas.sql
/*
 * Read about graphile schemas here:
 * https://www.graphile.org/postgraphile/namespaces/#advice
 */

create schema pf_public;
comment on schema pf_public is
  E'Namespace for tables and functions exposed to GraphQL';

create schema pf_hidden;
comment on schema pf_hidden is
  E'Namespace for implementation details of the `pf_public` schema that are not intended to be exposed publicly';

create schema pf_private;
comment on schema pf_private is
  E'Namespace for private tables and functions that should not be publicly accessible. Users need a `SECURITY DEFINER` function that selectively grants access to the namespace';

--! split: 0030-roles.sql
-- The 'anonymous' role (used by PostGraphile to represent an unauthenticated user) may
-- access the public, app_public and app_hidden schemas (but _NOT_ the
-- app_private schema).
grant usage on schema public, pf_public, pf_hidden to pf_visitor;

-- We only want the `anonymous` role to be able to insert rows (`serial` data type
-- creates sequences, so we need to grant access to that).
alter default privileges in schema public, pf_public, pf_hidden
  grant usage, select on sequences to pf_visitor;

-- And the `anonymous` role should be able to call functions too.
alter default privileges in schema public, pf_public, pf_hidden
  grant execute on functions to pf_visitor;

--! split: 0040-common-triggers.sql
/*
 * These triggers are commonly used across many tables.
 */

-- Used for queueing jobs easily; relies on the fact that every table we have
-- has a primary key 'id' column; this won't work if you rename your primary
-- key columns.
-- create function pf_private.tg__add_job() returns trigger as $$
-- begin
--   perform graphile_worker.add_job(tg_argv[0], json_build_object(
--     'schema', tg_table_schema,
--     'table', tg_table_name,
--     'op', tg_op,
--    'id', (case when tg_op = 'DELETE' then OLD.id else NEW.id end)
--  ));
--  return NEW;
--end;
--$$ language plpgsql volatile;
--comment on function pf_private.tg__add_job() is
--  E'Useful shortcut to create a job on insert/update. Pass the task name as the first trigger argument, and optionally the queue name as the second argument. The record id will automatically be available on the JSON payload.';

/*
 * This trigger is used on tables with created_at and updated_at to ensure that
 * these timestamps are kept valid (namely: `created_at` cannot be changed, and
 * `updated_at` must be monotonically increasing).
 */
-- create function pf_private.tg__timestamps() returns trigger as $$
-- begin
--   NEW.created_at = (case when TG_OP = 'INSERT' then NOW() else OLD.created_at end);
--   NEW.updated_at = (case when TG_OP = 'UPDATE' and OLD.updated_at >= NOW() then OLD.updated_at + interval '1 millisecond' else NOW() end);
--   return NEW;
-- end;
-- $$ language plpgsql volatile;
-- comment on function pf_private.tg__timestamps() is
--  E'This trigger should be called on all tables with created_at, updated_at - it ensures that they cannot be manipulated and that updated_at will always be larger than the previous updated_at.';

--! split: 0100-enum-tables.sql
-- Store valid dataset models as a table
-- https://stackoverflow.com/a/41655273
create table if not exists pf_public.pf_dataset_models (
  model text primary key
);
comment on table pf_public.pf_dataset_models is
  E'Table for referencing valid climate dataset model names';

insert into pf_public.pf_dataset_models (model) values
  ('GCM, CMIP5'),
  ('RCM, global REMO'),
  ('RCM, regional REMO');

grant select on table pf_public.pf_dataset_models to pf_visitor;

create table if not exists pf_public.pf_dataset_units (
  unit text primary key,
  unit_long text
);
comment on table pf_public.pf_dataset_units is
  E'Table for referencing valid climate dataset unit types';

insert into pf_public.pf_dataset_units (unit, unit_long) values
  ('days', 'Number of days'),
  ('temperature (°C)', null),
  ('class', null);

grant select on table pf_public.pf_dataset_units to pf_visitor;

create table if not exists pf_public.pf_dataset_categories (
  category text primary key
);
comment on table pf_public.pf_dataset_categories is
  E'Table for referencing valid climate dataset category names';

-- we'll add drought, fire and precipitation when those datasets are available
insert into pf_public.pf_dataset_categories (category) values
  ('basics'),
  ('increasing heat'),
  ('decreasing cold'),
  ('heat and humidity');

grant select on table pf_public.pf_dataset_categories to pf_visitor;

create table pf_public.pf_map_statuses (
  status text primary key
);
comment on table pf_public.pf_map_statuses is
  E'Table for referencing valid map publishing statues';

insert into pf_public.pf_map_statuses (status) values
 ('draft'),
 ('published');

grant select on table pf_public.pf_map_statuses to pf_visitor;

-- citext is case-insensitive
create domain pf_public.hex_color as citext check (
  value ~ '^#([0-9a-f]){3}(([0-9a-f]){3})?$'
);

comment on domain pf_public.hex_color is
  E'Hex colors must be a case insensitive string of 3 or 6 alpha-numeric characters prefixed with a `#`';

--! split: 0200-main-tables.sql
create table if not exists pf_public.pf_datasets (
  -- use internal id as primary key
  id integer unique primary key,
  name text not null,
  slug text not null,
  description text,
  resolution varchar(50),
  description_baseline text,
  field_name_baseline text,
  description_1C text,
  field_name_1C text,
  description_1_5C text,
  field_name_1_5C text,
  description_2C text,
  field_name_2C text,
  description_2_5C text,
  field_name_2_5C text,
  description_3C text,
  field_name_3C text,
  category text references pf_public.pf_dataset_categories(category) on update cascade,
  model text references pf_public.pf_dataset_models(model) on update cascade,
  unit text references pf_public.pf_dataset_units(unit) on update cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index pf_dataset_category_idx on pf_public.pf_datasets(category);
create index pf_dataset_model_idx on pf_public.pf_datasets(model);
create index pf_dataset_unit_idx on pf_public.pf_datasets(unit);

grant select on table pf_public.pf_datasets to pf_visitor;

-- create trigger _500_import
--   after insert on pf_public.pf_datasets
--   for each row
--   execute procedure pf_private.tg__add_job('import__woodwell_dataset');

-- create trigger _100_timestamps
--   before insert or update on pf_public.pf_datasets
--   for each row
--   execute procedure pf_private.tg__timestamps();

create table if not exists pf_public.pf_maps (
  id uuid default gen_random_uuid() primary key,
  dataset_id integer not null references pf_public.pf_datasets(id),
  map_style_id varchar(50) unique,
  name text not null,
  description text,
  bins integer[],
  status text not null default 'draft' references pf_public.pf_map_statuses(status),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- create trigger _100_timestamps
--   before insert or update on pf_public.pf_maps
--   for each row
--   execute procedure pf_private.tg__timestamps();

create index pf_map_dataset_idx on pf_public.pf_maps (dataset_id);
create index pf_map_status_idx on pf_public.pf_maps (status);

grant select on table pf_public.pf_maps to pf_visitor;

create table if not exists pf_public.pf_climate_data (
  id uuid default gen_random_uuid() primary key,
  dataset_id integer not null references pf_public.pf_datasets(id),
  coordinates geography(Point, 4326) not null,
  data_baseline_mean numeric(4,1),
  data_baseline_pctl10 numeric(4,1),
  data_baseline_pctl90 numeric(4,1),
  data_1C_mean numeric(4,1),
  data_1C_pctl10 numeric(4,1),
  data_1C_pctl90 numeric(4,1),
  data_1_5C_mean numeric(4,1),
  data_1_5C_pctl10 numeric(4,1),
  data_1_5C_pctl90 numeric(4,1),
  data_2C_mean numeric(4,1),
  data_2C_pctl10 numeric(4,1),
  data_2C_pctl90 numeric(4,1),
  data_2_5C_mean numeric(4,1),
  data_2_5C_pctl10 numeric(4,1),
  data_2_5C_pctl90 numeric(4,1),
  data_3C_mean numeric(4,1),
  data_3C_pctl10 numeric(4,1),
  data_3C_pctl90 numeric(4,1)
);

create index pf_climate_dataset_idx on pf_public.pf_climate_data (dataset_id);
create index pf_climate_coordinates_idx on pf_public.pf_climate_data (coordinates);

grant select on table pf_public.pf_climate_data to pf_authenticated;

--! Previous: sha1:bdeb7e5c3fab50162779f6474c0ccefb845c6118
--! Hash: sha1:c6ee1b8adfc031f6ea9c1ae1fee42228e00c6404

--! split: 0300-insert-pf-datasets.sql
-- Add Woodwell Dataset
insert into pf_public.pf_datasets (
  id,
  name,
  slug,
  category,
  model,
  resolution,
  unit,
  description,
  description_baseline,
  field_name_baseline,
  description_1C,
  field_name_1C,
  description_1_5C,
  field_name_1_5C,
  description_2C,
  field_name_2C,
  description_2_5C,
  field_name_2_5C,
  description_3C,
  field_name_3C
)
values (
    10105,
    'Number of days maximum temperature above 32°C (90°F)',
    'max-temp-32days-gcm',
    'increasing heat',
    'GCM, CMIP5',
    '240,120&167,167',
    'days',
    'The number of days with a daily maximum temperature exceeding 32 °C during any given year was averaged across 26 CMIP5 global climate models with 139 km x 105 km cells. Rather than expressing time in days, we consider how the world will look as we surpass thresholds in global temperature anomalies (1.0 °C, 1.5 °C, 2.0 °C, 2.5 °C, and 3.0 °C) relative to the preindustrial period (1850-1900). While the baseline data is averaged over 50 years, the data at different thresholds is averaged over 21 years, centered on the year each model surpasses the global temperature anomaly.\nNote that global climate models struggle to capture and underestimate temperature extremes near the coasts. The large cell sizes often average both land and ocean surface temperatures, incorporating lower ocean temperatures in coastal projections.',
    'Number of days maximum temperature above 32°C (90°F) in 1971-2000',
    'days_maxtemp_over_32C_1971-2000',
    'Number of days maximum temperature above 32°C (90°F) in a 1 °C world',
    'days_maxtemp_over_32C_1C',
    'Number of days maximum temperature above 32°C (90°F) in a 1.5 °C world',
    'days_maxtemp_over_32C_1_5C',
    'Number of days maximum temperature above 32°C (90°F) in a 2 °C world',
    'days_maxtemp_over_32C_2C',
    'Number of days maximum temperature above 32°C (90°F) in a 2.5 °C world',
    'days_maxtemp_over_32C_2_5C',
    'Number of days maximum temperature above 32°C (90°F) in a 3 °C world',
    'days_maxtemp_over_32C_3C'
), (
    20104,
    'Number of days maximum temperature above 32°C (90°F)',
    'max-temp-32days-remo',
    'basics',
    'RCM, global REMO',
    '1800,901&22,22',
    'days',
    'As mean global temperatures rise, local climates will experience extreme temperatures more frequently. For each warming scenario, the number of days exceeding 32°C are identified from daily maximum temperature projected by climate models. The displayed frequencies are averaged across 3 climate models and 21 years, so actual frequency outcomes could be higher or lower than the displayed value at each cell.',
    'Probable Futures uses the CORDEX REMO2015 regional climate modeling. 1971-2000 is the earliest time period for which results are available from this system of models. The average surface temperature during these years was approximately 0.5°C above that of 1850-1900.',
    'days_maxtemp_over_32C_1971-2000',
    'In 2017 the average surface temperature passed 1.0°C above the 1850-1900 average. Humans have only experienced higher temperatures during a brief period 120,000 years ago. Major biotic changes, including release of greenhouse gasses from thawing permafrost, forest fires, and collapse of Arctic sea ice, have begun contributing to further warming.',
    'days_maxtemp_over_32C_1C',
    'We should assume 1.5°C is reached soon. On the current path of emissions, this will happen around 2031. Limiting warming to 1.5°C would require both immediate radical transformation of economic activity and immediate, unprecedented expansion of carbon sequestering, especially forest growth. Society must prepare for higher temperatures.',
    'days_maxtemp_over_32C_1_5C',
    'On the current path of emissions, 2.0°C will be passed around 2044. Limiting warming to 2.0°C has been a policy “target” as many thought the atmosphere would be stable at this temperature. We now know that to maintain a 2.0°C average temperature, society will need to not only rapidly eliminate all human carbon emissions but also plan to withdraw carbon from the atmosphere in perpetuity.',
    'days_maxtemp_over_32C_2C',
    'On the current path of emissions, 2.5°C will be passed around 2055. The Earth’s atmosphere was last this warm nearly 3 million years ago, before the current Pleistocene era. At this temperature there were no land-based ice sheets other than on Antarctica and Greenland. Maintaining a stable temperature of 2.5° will require humans to constantly offset biotic sources of warming.',
    'days_maxtemp_over_32C_2_5C',
    'On the current path of emission, 3.0°C will be passed around 2067. At this level of warming, most regions of the Earth will have entered a different climate, causing severe biological disruptions. The atmosphere is extremely unlikely to be stable at this temperature.',
    'days_maxtemp_over_32C_3C'
  ),
  (
    20105,
    'Number of days maximum temperature above 35°C (95°F)',
    'max-temp-35days-remo',
    'increasing heat',
    'RCM, global REMO',
    '1800,901&22,22',
    'days',
    'As mean global temperatures rise, local climates will experience extreme temperatures more frequently. For each warming scenario, the number of days exceeding 35°C are identified from daily maximum temperature projected by climate models. The displayed frequencies are averaged across 3 climate models and 21 years, so actual frequency outcomes could be higher or lower than the displayed value at each cell.',
    'Probable Futures uses the CORDEX REMO2015 regional climate modeling. 1971-2000 is the earliest time period for which results are available from this system of models. The average surface temperature during these years was approximately 0.5°C above that of 1850-1900.',
    'days_maxtemp_over_35C_1971-2000',
    'In 2017 the average surface temperature passed 1.0°C above the 1850-1900 average. Humans have only experienced higher temperatures during a brief period 120,000 years ago. Major biotic changes, including release of greenhouse gasses from thawing permafrost, forest fires, and collapse of Arctic sea ice, have begun contributing to further warming.',
    'days_maxtemp_over_35C_1C',
    'We should assume 1.5°C is reached soon. On the current path of emissions, this will happen around 2031. Limiting warming to 1.5°C would require both immediate radical transformation of economic activity and immediate, unprecedented expansion of carbon sequestering, especially forest growth. Society must prepare for higher temperatures.',
    'days_maxtemp_over_35C_1_5C',
    'On the current path of emissions, 2.0°C will be passed around 2044. Limiting warming to 2.0°C has been a policy “target” as many thought the atmosphere would be stable at this temperature. We now know that to maintain a 2.0°C average temperature, society will need to not only rapidly eliminate all human carbon emissions but also plan to withdraw carbon from the atmosphere in perpetuity.',
    'days_maxtemp_over_35C_2C',
    'On the current path of emissions, 2.5°C will be passed around 2055. The Earth’s atmosphere was last this warm nearly 3 million years ago, before the current Pleistocene era. At this temperature there were no land-based ice sheets other than on Antarctica and Greenland. Maintaining a stable temperature of 2.5° will require humans to constantly offset biotic sources of warming.',
    'days_maxtemp_over_35C_2_5C',
    'On the current path of emission, 3.0°C will be passed around 2067. At this level of warming, most regions of the Earth will have entered a different climate, causing severe biological disruptions. The atmosphere is extremely unlikely to be stable at this temperature.',
    'days_maxtemp_over_35C_3C'
  ),
   (
    20106,
    'Number of days maximum temperature above 38°C (100°F)',
    'max-temp-38days-remo',
    'increasing heat',
    'RCM, global REMO',
    '1800,901&22,22',
    'days',
    'As mean global temperatures rise, local climates will experience extreme temperatures more frequently. For each warming scenario, the number of days exceeding 38°C are identified from daily maximum temperature projected by climate models. The displayed frequencies are averaged across 3 climate models and 21 years, so actual frequency outcomes could be higher or lower than the displayed value at each cell.',
    'Probable Futures uses the CORDEX REMO2015 regional climate modeling. 1971-2000 is the earliest time period for which results are available from this system of models. The average surface temperature during these years was approximately 0.5°C above that of 1850-1900.',
    'days_maxtemp_over_38C_1971-2000',
    'In 2017 the average surface temperature passed 1.0°C above the 1850-1900 average. Humans have only experienced higher temperatures during a brief period 120,000 years ago. Major biotic changes, including release of greenhouse gasses from thawing permafrost, forest fires, and collapse of Arctic sea ice, have begun contributing to further warming.',
    'days_maxtemp_over_38C_1C',
    'We should assume 1.5°C is reached soon. On the current path of emissions, this will happen around 2031. Limiting warming to 1.5°C would require both immediate radical transformation of economic activity and immediate, unprecedented expansion of carbon sequestering, especially forest growth. Society must prepare for higher temperatures.',
    'days_maxtemp_over_38C_1_5C',
    'On the current path of emissions, 2.0°C will be passed around 2044. Limiting warming to 2.0°C has been a policy “target” as many thought the atmosphere would be stable at this temperature. We now know that to maintain a 2.0°C average temperature, society will need to not only rapidly eliminate all human carbon emissions but also plan to withdraw carbon from the atmosphere in perpetuity.',
    'days_maxtemp_over_38C_2C',
    'On the current path of emissions, 2.5°C will be passed around 2055. The Earth’s atmosphere was last this warm nearly 3 million years ago, before the current Pleistocene era. At this temperature there were no land-based ice sheets other than on Antarctica and Greenland. Maintaining a stable temperature of 2.5° will require humans to constantly offset biotic sources of warming.',
    'days_maxtemp_over_38C_2_5C',
    'On the current path of emission, 3.0°C will be passed around 2067. At this level of warming, most regions of the Earth will have entered a different climate, causing severe biological disruptions. The atmosphere is extremely unlikely to be stable at this temperature.',
    'days_maxtemp_over_38C_3C'
  ),
  (
    20202,
    'Number of days minimum temperature below 0°C (32°F)',
    'min-temp-0days-remo',
    'basics',
    'RCM, global REMO',
    '1800,901&22,22',
    'days',
    '“Frost nights” measures the number of days per year that have a minimum temperature below freezing (0°C or 32°F).  The lowest temperature during a day happens at night, when temperatures dip after sunset. “Frost nights” are a proxy of the length and consistency of the cold season, particularly at mid and high latitudes. As mean global temperatures rise, local climates will experience fewer frost nights.  For each warming scenario, the number of days below 0°C are identified from daily minimum temperature projected by climate models. The displayed frequencies are averaged across 3 climate models and 21 years, so actual frequency outcomes could be higher or lower than the displayed value at each cell.',
    'Probable Futures uses the CORDEX REMO2015 regional climate modeling. 1971-2000 is the earliest time period for which results are available from this system of models. The average surface temperature during these years was approximately 0.5°C above that of 1850-1900.',
    'days_mintemp_under_0C_1971-2000',
    'In 2017 the average surface temperature passed 1.0°C above the 1850-1900 average. Humans have only experienced higher temperatures during a brief period 120,000 years ago. Major biotic changes, including release of greenhouse gasses from thawing permafrost, forest fires, and collapse of Arctic sea ice, have begun contributing to further warming.',
    'days_mintemp_under_0C_1C',
    'We should assume 1.5°C is reached soon. On the current path of emissions, this will happen around 2031. Limiting warming to 1.5°C would require both immediate radical transformation of economic activity and immediate, unprecedented expansion of carbon sequestering, especially forest growth. Society must prepare for higher temperatures.',
    'days_mintemp_under_0C_1_5C',
    'On the current path of emissions, 2.0°C will be passed around 2044. Limiting warming to 2.0°C has been a policy “target” as many thought the atmosphere would be stable at this temperature. We now know that to maintain a 2.0°C average temperature, society will need to not only rapidly eliminate all human carbon emissions but also plan to withdraw carbon from the atmosphere in perpetuity.',
    'days_mintemp_under_0C_2C',
    'On the current path of emissions, 2.5°C will be passed around 2055. The Earth’s atmosphere was last this warm nearly 3 million years ago, before the current Pleistocene era. At this temperature there were no land-based ice sheets other than on Antarctica and Greenland. Maintaining a stable temperature of 2.5° will require humans to constantly offset biotic sources of warming.',
    'days_mintemp_under_0C_2_5C',
    'On the current path of emission, 3.0°C will be passed around 2067. At this level of warming, most regions of the Earth will have entered a different climate, causing severe biological disruptions. The atmosphere is extremely unlikely to be stable at this temperature.',
    'days_mintemp_under_0C_3C'
  ),
 (
    20203,
    'Number of days minimum temperature above 20°C (68°F)',
    'min-temp-20days-remo',
    'decreasing cold',
    'RCM, global REMO',
    '1800,901&22,22',
    'days',
    '“Nights above 20°C” measures how many days in a year have a minimum temperature exceeding 20°C (68°F) for each warming scenario. The lowest temperature during a day happens at night when temperatures dip after sunset. The human experience of a “hot” night is relative to location, so a threshold of 20°C is often used for higher latitudes (Europe and the US) and a threshold of 25°C is often used for tropical and equatorial regions. The displayed frequencies of nights exceeding 20°C are averaged across 3 climate models and 21 years, so actual frequency outcomes could be higher or lower than the displayed value at each cell.',
    'Probable Futures uses the CORDEX REMO2015 regional climate modeling. 1971-2000 is the earliest time period for which results are available from this system of models. The average surface temperature during these years was approximately 0.5°C above that of 1850-1900.',
    'days_mintemp_above_20C_1971-2000',
    'In 2017 the average surface temperature passed 1.0°C above the 1850-1900 average. Humans have only experienced higher temperatures during a brief period 120,000 years ago. Major biotic changes, including release of greenhouse gasses from thawing permafrost, forest fires, and collapse of Arctic sea ice, have begun contributing to further warming.',
    'days_mintemp_above_20C_1C',
    'We should assume 1.5°C is reached soon. On the current path of emissions, this will happen around 2031. Limiting warming to 1.5°C would require both immediate radical transformation of economic activity and immediate, unprecedented expansion of carbon sequestering, especially forest growth. Society must prepare for higher temperatures.',
    'days_mintemp_above_20C_1_5C',
    'On the current path of emissions, 2.0°C will be passed around 2044. Limiting warming to 2.0°C has been a policy “target” as many thought the atmosphere would be stable at this temperature. We now know that to maintain a 2.0°C average temperature, society will need to not only rapidly eliminate all human carbon emissions but also plan to withdraw carbon from the atmosphere in perpetuity.',
    'days_mintemp_above_20C_2C',
    'On the current path of emissions, 2.5°C will be passed around 2055. The Earth’s atmosphere was last this warm nearly 3 million years ago, before the current Pleistocene era. At this temperature there were no land-based ice sheets other than on Antarctica and Greenland. Maintaining a stable temperature of 2.5° will require humans to constantly offset biotic sources of warming.',
    'days_mintemp_above_20C_2_5C',
    'On the current path of emission, 3.0°C will be passed around 2067. At this level of warming, most regions of the Earth will have entered a different climate, causing severe biological disruptions. The atmosphere is extremely unlikely to be stable at this temperature.',
    'days_mintemp_above_20C_3C'
  ),
  (
    20204,
    'Number of days minimum temperature above 25°C (77°F)',
    'min-temp-25days-remo',
    'decreasing cold',
    'RCM, global REMO',
    '1800,901&22,22',
    'days',
    '“Nights above 25°C” measures how many days in a year have a minimum temperature exceeding 25°C (77°F) for each warming scenario. The lowest temperature during a day happens at night when temperatures dip after sunset. The human experience of a “hot” night is relative to location, so a threshold of 20°C is often used for higher latitudes (Europe and the US) and a threshold of 25°C is often used for tropical and equatorial regions. The displayed frequencies of nights exceeding 25°C are averaged across 3 climate models and 21 years, so actual frequency outcomes could be higher or lower than the displayed value at each cell.',
    null,
    'days_mintemp_above_25C_1971-2000',
    null,
    'days_mintemp_above_25C_1C',
    null,
    'days_mintemp_above_25C_1_5C',
    null,
    'days_mintemp_above_25C_2C',
    null,
    'days_mintemp_above_25C_2_5C',
    null,
    'days_mintemp_above_25C_3C'
  ),
  (
    20205,
    'Number of days maximum temperature below 0°C (32°F)',
    'max-temp-0days-remo',
    'decreasing cold',
    'RCM, global REMO',
    '1800,901&22,22',
    'days',
    '“Freezing days” measures the number of days per year that remain below freezing all day, or have a maximum temperature below freezing (0°C or 32°F).  “Freezing days” are a proxy of the length and consistency of the cold season, particularly at mid and high latitudes. As mean global temperatures rise, local climates will experience fewer freezing days.  For each warming scenario, the number of days below 0°C are identified from daily maximum temperature projected by climate models. The displayed frequencies are averaged across 3 climate models and 21 years, so actual frequency outcomes could be higher or lower than the displayed value at each cell.',
    'Probable Futures uses the CORDEX REMO2015 regional climate modeling. 1971-2000 is the earliest time period for which results are available from this system of models. The average surface temperature during these years was approximately 0.5°C above that of 1850-1900.',
    'days_maxtemp_under_0C_1971-2000',
    'In 2017 the average surface temperature passed 1.0°C above the 1850-1900 average. Humans have only experienced higher temperatures during a brief period 120,000 years ago. Major biotic changes, including release of greenhouse gasses from thawing permafrost, forest fires, and collapse of Arctic sea ice, have begun contributing to further warming.',
    'days_maxtemp_under_0C_1C',
    'We should assume 1.5°C is reached soon. On the current path of emissions, this will happen around 2031. Limiting warming to 1.5°C would require both immediate radical transformation of economic activity and immediate, unprecedented expansion of carbon sequestering, especially forest growth. Society must prepare for higher temperatures.',
    'days_maxtemp_under_0C_1_5C',
    'On the current path of emissions, 2.0°C will be passed around 2044. Limiting warming to 2.0°C has been a policy “target” as many thought the atmosphere would be stable at this temperature. We now know that to maintain a 2.0°C average temperature, society will need to not only rapidly eliminate all human carbon emissions but also plan to withdraw carbon from the atmosphere in perpetuity.',
    'days_maxtemp_under_0C_2C',
    'On the current path of emissions, 2.5°C will be passed around 2055. The Earth’s atmosphere was last this warm nearly 3 million years ago, before the current Pleistocene era. At this temperature there were no land-based ice sheets other than on Antarctica and Greenland. Maintaining a stable temperature of 2.5° will require humans to constantly offset biotic sources of warming.',
    'days_maxtemp_under_0C_2_5C',
    'On the current path of emission, 3.0°C will be passed around 2067. At this level of warming, most regions of the Earth will have entered a different climate, causing severe biological disruptions. The atmosphere is extremely unlikely to be stable at this temperature.',
    'days_maxtemp_under_0C_3C'
  ),
  (
    20301,
    'Number of days maximum wet-bulb temperature above 26°C',
    'wetbulb-26days-remo',
    'basics',
    'RCM, global REMO',
    '1800,901&22,22',
    'days',
    'Wet-bulb temperature can be calculated using temperature and humidity. High wet-bulb temperatures can impair the human body’s ability to self-cool through sweating. 26°C or 79°F wet-bulb can occur at 30°C air temperature and 75% relative humidity, or 38°C  and 36% humidity. For each warming scenario, the number of days exceeding 26°C wet-bulb are identified from daily maximum wet-bulb temperatures computed using daily maximum temperature and daily minimum relative humidity, variables that are projected by climate models. The displayed frequencies are averaged across 3 climate models and 21 years, so actual frequency outcomes could be higher or lower than the displayed value at each cell.',
    'Probable Futures uses the CORDEX REMO2015 regional climate modeling. 1971-2000 is the earliest time period for which results are available from this system of models. The average surface temperature during these years was approximately 0.5°C above that of 1850-1900.',
    'days_maxwetbulb_over_26C_1971-2000',
    'In 2017 the average surface temperature passed 1.0°C above the 1850-1900 average. Humans have only experienced higher temperatures during a brief period 120,000 years ago. Major biotic changes, including release of greenhouse gasses from thawing permafrost, forest fires, and collapse of Arctic sea ice, have begun contributing to further warming.',
    'days_maxwetbulb_over_26C_1C',
    'We should assume 1.5°C is reached soon. On the current path of emissions, this will happen around 2031. Limiting warming to 1.5°C would require both immediate radical transformation of economic activity and immediate, unprecedented expansion of carbon sequestering, especially forest growth. Society must prepare for higher temperatures.',
    'days_maxwetbulb_over_26C_1_5C',
    'On the current path of emissions, 2.0°C will be passed around 2044. Limiting warming to 2.0°C has been a policy “target” as many thought the atmosphere would be stable at this temperature. We now know that to maintain a 2.0°C average temperature, society will need to not only rapidly eliminate all human carbon emissions but also plan to withdraw carbon from the atmosphere in perpetuity.',
    'days_maxwetbulb_over_26C_2C',
    'On the current path of emissions, 2.5°C will be passed around 2055. The Earth’s atmosphere was last this warm nearly 3 million years ago, before the current Pleistocene era. At this temperature there were no land-based ice sheets other than on Antarctica and Greenland. Maintaining a stable temperature of 2.5° will require humans to constantly offset biotic sources of warming.',
    'days_maxwetbulb_over_26C_2_5C',
    'On the current path of emission, 3.0°C will be passed around 2067. At this level of warming, most regions of the Earth will have entered a different climate, causing severe biological disruptions. The atmosphere is extremely unlikely to be stable at this temperature.',
    'days_maxwetbulb_over_26C_3C'
  ),
  (
    20302,
    'Number of days maximum wet-bulb temperature above 28°C',
    'wetbulb-28days-remo',
    'heat and humidity',
    'RCM, global REMO',
    '1800,901&22,22',
    'days',
    'Wet-bulb temperature can be calculated using temperature and humidity. High wet-bulb temperatures can impair the human body’s ability to self-cool through sweating. 28°C or 82°F wet-bulb can occur at 30°C air temperature and 85% relative humidity, or 38°C  and 45% humidity. For each warming scenario, the number of days exceeding 28°C wet-bulb are identified from daily maximum wet-bulb temperatures computed using daily maximum temperature and daily minimum relative humidity, variables that are projected by climate models. The displayed frequencies are averaged across 3 climate models and 21 years, so actual frequency outcomes could be higher or lower than the displayed value at each cell.',
    'Probable Futures uses the CORDEX REMO2015 regional climate modeling. 1971-2000 is the earliest time period for which results are available from this system of models. The average surface temperature during these years was approximately 0.5°C above that of 1850-1900.',
    'days_maxwetbulb_over_28C_1971-2000',
    'In 2017 the average surface temperature passed 1.0°C above the 1850-1900 average. Humans have only experienced higher temperatures during a brief period 120,000 years ago. Major biotic changes, including release of greenhouse gasses from thawing permafrost, forest fires, and collapse of Arctic sea ice, have begun contributing to further warming.',
    'days_maxwetbulb_over_28C_1C',
    'We should assume 1.5°C is reached soon. On the current path of emissions, this will happen around 2031. Limiting warming to 1.5°C would require both immediate radical transformation of economic activity and immediate, unprecedented expansion of carbon sequestering, especially forest growth. Society must prepare for higher temperatures.',
    'days_maxwetbulb_over_28C_1_5C',
    'On the current path of emissions, 2.0°C will be passed around 2044. Limiting warming to 2.0°C has been a policy “target” as many thought the atmosphere would be stable at this temperature. We now know that to maintain a 2.0°C average temperature, society will need to not only rapidly eliminate all human carbon emissions but also plan to withdraw carbon from the atmosphere in perpetuity.',
    'days_maxwetbulb_over_28C_2C',
    'On the current path of emissions, 2.5°C will be passed around 2055. The Earth’s atmosphere was last this warm nearly 3 million years ago, before the current Pleistocene era. At this temperature there were no land-based ice sheets other than on Antarctica and Greenland. Maintaining a stable temperature of 2.5° will require humans to constantly offset biotic sources of warming.',
    'days_maxwetbulb_over_28C_2_5C',
    'On the current path of emission, 3.0°C will be passed around 2067. At this level of warming, most regions of the Earth will have entered a different climate, causing severe biological disruptions. The atmosphere is extremely unlikely to be stable at this temperature.',
    'days_maxwetbulb_over_28C_3C'
  ),
  (
    20303,
    'Number of days maximum wet-bulb temperature above 30°C',
    'wetbulb-30days-remo',
    'heat and humidity',
    'RCM, global REMO',
    '1800,901&22,22',
    'days',
    'Wet-bulb temperature can be calculated using temperature and humidity. High wet-bulb temperatures can impair the human body’s ability to self-cool through sweating. 30°C or 86°F wet-bulb can occur at 32 °C air temperature and 86% relative humidity, or 38°C  and 54% humidity. For each warming scenario, the number of days exceeding 30°C wet-bulb are identified from daily maximum wet-bulb temperatures computed using daily maximum temperature and daily minimum relative humidity, variables that are projected by climate models. The displayed frequencies are averaged across 3 climate models and 21 years, so actual frequency outcomes could be higher or lower than the displayed value at each cell.',
    'Probable Futures uses the CORDEX REMO2015 regional climate modeling. 1971-2000 is the earliest time period for which results are available from this system of models. The average surface temperature during these years was approximately 0.5°C above that of 1850-1900.',
    'days_maxwetbulb_over_30C_1971-2000',
    'In 2017 the average surface temperature passed 1.0°C above the 1850-1900 average. Humans have only experienced higher temperatures during a brief period 120,000 years ago. Major biotic changes, including release of greenhouse gasses from thawing permafrost, forest fires, and collapse of Arctic sea ice, have begun contributing to further warming.',
    'days_maxwetbulb_over_30C_1C',
    'We should assume 1.5°C is reached soon. On the current path of emissions, this will happen around 2031. Limiting warming to 1.5°C would require both immediate radical transformation of economic activity and immediate, unprecedented expansion of carbon sequestering, especially forest growth. Society must prepare for higher temperatures.',
    'days_maxwetbulb_over_30C_1_5C',
    'On the current path of emissions, 2.0°C will be passed around 2044. Limiting warming to 2.0°C has been a policy “target” as many thought the atmosphere would be stable at this temperature. We now know that to maintain a 2.0°C average temperature, society will need to not only rapidly eliminate all human carbon emissions but also plan to withdraw carbon from the atmosphere in perpetuity.',
    'days_maxwetbulb_over_30C_2C',
    'On the current path of emissions, 2.5°C will be passed around 2055. The Earth’s atmosphere was last this warm nearly 3 million years ago, before the current Pleistocene era. At this temperature there were no land-based ice sheets other than on Antarctica and Greenland. Maintaining a stable temperature of 2.5° will require humans to constantly offset biotic sources of warming.',
    'days_maxwetbulb_over_30C_2_5C',
    'On the current path of emission, 3.0°C will be passed around 2067. At this level of warming, most regions of the Earth will have entered a different climate, causing severe biological disruptions. The atmosphere is extremely unlikely to be stable at this temperature.',
    'days_maxwetbulb_over_30C_3C'
  ),
 (
    20304,
    'Number of days maximum wet-bulb temperature above 32°C',
    'wetbulb-32days-remo',
    'heat and humidity',
    'RCM, global REMO',
    '1800,901&22,22',
    'days',
    'Wet-bulb temperature can be calculated using temperature and humidity. High wet-bulb temperatures can impair the human body’s ability to self-cool through sweating. 32°C or 90°F wet-bulb can occur at 32 °C air temperature and 99% relative humidity, or 40°C  and 55% humidity. For each warming scenario, the number of days exceeding 32°C wet-bulb are identified from daily maximum wet-bulb temperatures computed using daily maximum temperature and daily minimum relative humidity, variables that are projected by climate models. The displayed frequencies are averaged across 3 climate models and 21 years, so actual frequency outcomes could be higher or lower than the displayed value at each cell.',
    'Probable Futures uses the CORDEX REMO2015 regional climate modeling. 1971-2000 is the earliest time period for which results are available from this system of models. The average surface temperature during these years was approximately 0.5°C above that of 1850-1900.',
    'days_maxwetbulb_over_32C_1971-2000',
    'In 2017 the average surface temperature passed 1.0°C above the 1850-1900 average. Humans have only experienced higher temperatures during a brief period 120,000 years ago. Major biotic changes, including release of greenhouse gasses from thawing permafrost, forest fires, and collapse of Arctic sea ice, have begun contributing to further warming.',
    'days_maxwetbulb_over_32C_1C',
    'We should assume 1.5°C is reached soon. On the current path of emissions, this will happen around 2031. Limiting warming to 1.5°C would require both immediate radical transformation of economic activity and immediate, unprecedented expansion of carbon sequestering, especially forest growth. Society must prepare for higher temperatures.',
    'days_maxwetbulb_over_32C_1_5C',
    'On the current path of emissions, 2.0°C will be passed around 2044. Limiting warming to 2.0°C has been a policy “target” as many thought the atmosphere would be stable at this temperature. We now know that to maintain a 2.0°C average temperature, society will need to not only rapidly eliminate all human carbon emissions but also plan to withdraw carbon from the atmosphere in perpetuity.',
    'days_maxwetbulb_over_32C_2C',
    'On the current path of emissions, 2.5°C will be passed around 2055. The Earth’s atmosphere was last this warm nearly 3 million years ago, before the current Pleistocene era. At this temperature there were no land-based ice sheets other than on Antarctica and Greenland. Maintaining a stable temperature of 2.5° will require humans to constantly offset biotic sources of warming.',
    'days_maxwetbulb_over_32C_2_5C',
    'On the current path of emission, 3.0°C will be passed around 2067. At this level of warming, most regions of the Earth will have entered a different climate, causing severe biological disruptions. The atmosphere is extremely unlikely to be stable at this temperature.',
    'days_maxwetbulb_over_32C_3C'
  );

--! Previous: sha1:c6ee1b8adfc031f6ea9c1ae1fee42228e00c6404
--! Hash: sha1:296a76ba1b3486cd6cbb3b32cf573ed1c4f56674

--! split: 1-partner-platform-tables.sql
-- These will likely change
create table if not exists pf_public.pf_partner_projects (
  id uuid default gen_random_uuid() primary key,
  name text not null,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create table if not exists pf_public.pf_partner_datasets (
  id uuid default gen_random_uuid() primary key,
  name text not null,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create table if not exists pf_public.pf_partner_project_datasets (
  project_id uuid not null references pf_public.pf_partner_projects on delete cascade,
  dataset_id uuid not null references pf_public.pf_partner_datasets on delete cascade
);

create table if not exists pf_public.pf_partner_dataset_uploads (
  id uuid default gen_random_uuid() primary key,
  s3_url text,
  partner_dataset_id uuid not null references pf_public.pf_partner_datasets on delete cascade,
  created_at timestamptz not null default now()
);

import { Pool } from "pg";

const env = require("dotenv").config();

if (env.error) {
  throw env.error;
}

/**
 * When a PoolClient omits an 'error' event that cannot be caught by a promise
 * chain (e.g. when the PostgreSQL server terminates the link but the client
 * isn't actively being used) the error is raised via the Pool. In Node.js if
 * an 'error' event is raised and it isn't handled, the entire process exits.
 * This NOOP handler avoids this occurring on our pools.
 *
 */
function swallowPoolError(e: any) {
  console.error("swallowing PgPool error: %o", e);
}

export const pgPool = new Pool({
  user: process.env["PG_USER"],
  password: process.env["PG_PASSWORD"],
  host: process.env["PG_HOST"],
  database: process.env["PG_DBNAME"],
  port: parseInt(process.env["PG_PORT"] || "5432"),
  application_name: "loader",
});

pgPool.on("error", swallowPoolError);

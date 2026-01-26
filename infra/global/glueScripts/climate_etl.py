import sys
import hashlib
import re
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import udf, col, input_file_name, substring
from pyspark.sql.types import StructType, StructField, StringType

args = getResolvedOptions(sys.argv, ['JOB_NAME', 'INPUT_PATH', 'OUTPUT_PATH'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

INPUT_PATH = args['INPUT_PATH']
OUTPUT_PATH = args['OUTPUT_PATH']


def round_coordinate(value):
    """
    Round coordinate to 1 decimal place and clean trailing zeros.
    Returns string representation.
    """
    if value is None:
        return None

    try:
        # Convert to float and round to 1 decimal
        rounded = round(float(str(value).strip()), 1)
        # Convert to string and remove trailing zeros
        string_val = str(rounded)
        return string_val.rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return None


def compute_grid_hash(lon, lat):
    """
    Accepts lon/lat as either strings or numeric types.
    Replicates: md5('RCM' || ST_AsEWKT(point))
    ST_AsEWKT format: 'SRID=4326;POINT(lon lat)'
    """
    GRID = "RCM"

    if lon is None or lat is None:
        return None

    # Round coordinates and clean trailing zeros
    lon_clean = round_coordinate(lon)
    lat_clean = round_coordinate(lat)

    if lon_clean is None or lat_clean is None:
        return None

    # Build EWKT
    ewkt = f"SRID=4326;POINT({lon_clean} {lat_clean})"
    combined = f"{GRID}{ewkt}"

    return hashlib.md5(combined.encode()).hexdigest()


compute_hash_udf = udf(compute_grid_hash, StringType())
round_coordinate_udf = udf(round_coordinate, StringType())


# UDF to parse filename and extract metadata
def parse_filename(filepath):
    """
    Extract metadata from filename like: var-tasmax_dom-NAM_wl-0.5_tile-234.csv
    Returns: (variable, domain, warming_scenario)
    """
    filename = filepath.split('/')[-1]

    # Extract variable (e.g., tasmax, tasmin)
    var_match = re.search(r'var-([^_]+)', filename)
    variable = var_match.group(1) if var_match else None

    # Extract domain (e.g., NAM, EUR)
    dom_match = re.search(r'dom-([^_]+)', filename)
    domain = dom_match.group(1) if dom_match else None

    # Extract warming scenario (e.g., 0.5, 1.0)
    wl_match = re.search(r'wl-([^_]+)', filename)
    warming_scenario = wl_match.group(1) if wl_match else None

    return (variable, domain, warming_scenario)


# Register UDF
parse_file_schema = StructType([
    StructField("variable", StringType(), True),
    StructField("domain", StringType(), True),
    StructField("warming_scenario", StringType(), True)
])

parse_filename_udf = udf(parse_filename, parse_file_schema)

# Read all CSVs from source
print("Reading CSVs from INPUT_PATH")

df = spark.read \
    .option("header", "true") \
    .option("inferSchema", "true") \
    .csv(f"{INPUT_PATH}/*.csv")

# Add filename for metadata extraction
df = df.withColumn("_filename", input_file_name())

# Parse filename to extract metadata
df = df.withColumn("_parsed", parse_filename_udf(col("_filename")))

# Split parsed tuple into columns (PySpark array split)
df = df.withColumn("variable", col("_parsed.variable")) \
    .withColumn("domain", col("_parsed.domain")) \
    .withColumn("warming_scenario", col("_parsed.warming_scenario"))

# Compute grid hash
df = df.withColumn("grid_hash", compute_hash_udf(col("lon"), col("lat")))

# Round and clean the coordinates to 1 decimal place
df = df.withColumn("lon_rounded", round_coordinate_udf(col("lon"))) \
    .withColumn("lat_rounded", round_coordinate_udf(col("lat")))

# Add hash prefix (first 2 characters)
df = df.withColumn("hash_prefix", substring(col("grid_hash"), 1, 2))

# Select and rename columns to match Athena schema
df_new = df.select(
    col("grid_hash"),
    col("lon_rounded").alias("lon"),
    col("lat_rounded").alias("lat"),
    col("value"),
    col("domain"),
    col("variable"),
    col("warming_scenario"),
    col("hash_prefix")
)

# Show sample for validation
print("Sample transformed data:")
df_new.show(5, truncate=False)
print(f"Total rows: {df_new.count()}")

print("Repartitioning by partition keys...")

# print("Coalescing to 1 file per partition...")
# df_final = df_new.repartition("variable", "warming_scenario", "hash_prefix")
# df_final = df_final.coalesce(1)

# instead of coalesce, we can consolidate based on number of records
spark.conf.set("spark.sql.files.maxRecordsPerFile", 5_000_000)
df_final = df_new.repartition(
    200,
    "variable", "warming_scenario", "hash_prefix"
)

print(f"Partitions before write: {df_final.rdd.getNumPartitions()}")

print(f"Writing to {OUTPUT_PATH}")
df_final.write \
    .mode("append") \
    .partitionBy("variable", "warming_scenario", "hash_prefix") \
    .parquet(OUTPUT_PATH, compression="snappy")

print("ETL job completed successfully")

job.commit()

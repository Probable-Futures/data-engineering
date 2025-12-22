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

args = getResolvedOptions(sys.argv, ['JOB_NAME', 'SOURCE_BUCKET', 'TARGET_BUCKET'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

SOURCE_BUCKET = args['SOURCE_BUCKET']
TARGET_BUCKET = args['TARGET_BUCKET']

def compute_grid_hash(lon, lat):
    """
    Accepts lon/lat as either strings or numeric types.
    Replicates: md5('RCM' || ST_AsEWKT(point))
    ST_AsEWKT format: 'SRID=4326;POINT(lon lat)'
    """
    GRID = "RCM"

    if lon is None or lat is None:
        return None

    # Convert to float if possible (string or numeric)
    try:
        lon_val = float(str(lon).strip())
        lat_val = float(str(lat).strip())
    except (ValueError, TypeError):
        return None

    # Round to 1 decimal and clean trailing zeros
    lon_string = str(round(lon_val, 1))
    lon_clean = lon_string.rstrip("0").rstrip(".")

    lat_string = str(round(lat_val, 1))
    lat_clean = lat_string.rstrip("0").rstrip(".")

    # Build EWKT
    ewkt = f"SRID=4326;POINT({lon_clean} {lat_clean})"
    combined = f"{GRID}{ewkt}"

    return hashlib.md5(combined.encode()).hexdigest()

compute_hash_udf = udf(compute_grid_hash, StringType())

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
print(f"Reading CSVs from s3://{SOURCE_BUCKET}/climate-data-full-model-raw/")
df = spark.read \
    .option("header", "true") \
    .option("inferSchema", "true") \
    .csv(f"s3://{SOURCE_BUCKET}/climate-data-full-model-raw/*.csv")

# Add filename for metadata extraction
df = df.withColumn("_filename", input_file_name())

# Parse filename to extract metadata
df = df.withColumn("_parsed", parse_filename_udf(col("_filename")))

# Split parsed tuple into columns (PySpark array split)
from pyspark.sql.functions import split
df = df.withColumn("variable", col("_parsed.variable")) \
       .withColumn("domain", col("_parsed.domain")) \
       .withColumn("warming_scenario", col("_parsed.warming_scenario"))

# Compute grid hash
df = df.withColumn("grid_hash", compute_hash_udf(col("lon"), col("lat")))

# Add hash prefix (first 2 characters)
df = df.withColumn("hash_prefix", substring(col("grid_hash"), 1, 2))

# Select and rename columns to match Athena schema
df_final = df.select(
    col("grid_hash"),
    col("lon"),
    col("lat"),
    col("value"),
    col("domain"),
    col("variable"),
    col("warming_scenario"),
    col("hash_prefix")
)

# Show sample for validation
print("Sample transformed data:")
df_final.show(5, truncate=False)
print(f"Total rows: {df_final.count()}")

# Write to S3 as partitioned Parquet
output_path = f"s3://{TARGET_BUCKET}/climate-data-full-model-raw-parquet/parquet-files/"
print(f"Writing to {output_path}")

df_final.write \
    .mode("overwrite") \
    .partitionBy("variable", "warming_scenario", "hash_prefix") \
    .parquet(output_path, compression="snappy")

print("ETL job completed successfully")
job.commit()
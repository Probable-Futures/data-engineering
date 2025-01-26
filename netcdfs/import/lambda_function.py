import os
import subprocess


def lambda_handler(event, context):
    dataset_id = event.get("dataset_id")
    netcdf_object_key = event.get("netcdf_object_key")

    if not dataset_id:
        raise ValueError("Missing required parameter: dataset_id")

    if not netcdf_object_key:
        raise ValueError("Missing required parameter: netcdf_object_key")

    command = [
        "python",
        "pfimport.py",
        "--mutate",
        "--dbhost",
        os.getenv("PG_HOST"),
        "--dbname",
        os.getenv("PG_DBNAME"),
        "--dbuser",
        os.getenv("PG_USER"),
        "--dbpassword",
        os.getenv("PG_PASSWORD"),
        "--load-one-cdf",
        dataset_id,
        "--netcdf-object-key",
        netcdf_object_key,
    ]

    try:
        # Run the command
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return {"statusCode": 200, "body": result.stdout}
    except subprocess.CalledProcessError as e:
        return {"statusCode": 500, "body": e.stderr}

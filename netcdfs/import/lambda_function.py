import os
import subprocess


def lambda_handler(event, context):
    dataset_id = event.get("dataset_id")
    netcdf_object_key = event.get("netcdf_object_key")
    batch = event.get("batch") or "1"
    batch_size = event.get("batch_size") or "1500000"
    add_dataset_record = event.get("add_dataset_record")

    if not dataset_id:
        raise ValueError("Missing required parameter: dataset_id")

    if not netcdf_object_key:
        raise ValueError("Missing required parameter: netcdf_object_key")

    # Normalize add_dataset_record to a boolean
    if isinstance(add_dataset_record, str):
        add_dataset_record = add_dataset_record.lower() == "true"

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
        "--batch",
        batch,
        "--batch-size",
        batch_size,
    ]

    if add_dataset_record:
        command.append("--add-dataset-record")

    try:
        # Run the command
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return {"statusCode": 200, "body": result.stdout}
    except subprocess.CalledProcessError as e:
        return {"statusCode": 500, "body": e.stderr}

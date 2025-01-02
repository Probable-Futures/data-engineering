import os
import subprocess
import boto3


def lambda_handler(event, context):
    dataset_id = event.get("dataset_id")
    dataset_version = event.get("dataset_version")

    if not dataset_id:
        raise ValueError("Missing required parameter: dataset_id")

    if not dataset_version:
        raise ValueError("Missing required parameter: dataset_version")

    env = os.environ.copy()
    env.update(
        {
            "PG_HOST": os.getenv("PG_HOST"),
            "PG_PORT": os.getenv("PG_PORT"),
            "PG_USER": os.getenv("PG_USER"),
            "PG_PASSWORD": os.getenv("PG_PASSWORD"),
            "PG_DBNAME": os.getenv("PG_DBNAME"),
        }
    )

    bucket_name = os.getenv("S3_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("Environment variable S3_BUCKET_NAME is not set")

    print(f"S3_BUCKET_NAME: {bucket_name}")

    target = f"/tmp/data/mapbox/mts/{dataset_id}.geojsonld"
    s3_key = f"climate-data-geojson/v{dataset_version}/{dataset_id}.geojsonld"

    # Run gmake with the specified target
    try:
        subprocess.run(["gmake", target], check=True, env=env)
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": str(e)}

    if not os.path.exists(target):
        return {"status": "error", "message": f"File not found: {target}"}

    file_size = os.path.getsize(target)
    print(f"File size: {file_size} bytes")

    s3_client = boto3.client("s3", region_name="us-west-2")

    config = boto3.s3.transfer.TransferConfig(
        multipart_threshold=100 * 1024 * 1024,  # 100 MB
        multipart_chunksize=10 * 1024 * 1024,  # 10 MB
    )
    print("copying to S3..")

    try:
        print(f"Uploading {target} to bucket {bucket_name} with key {s3_key}...")
        s3_client.upload_file(target, bucket_name, s3_key, Config=config)
        print("Upload successful.")
    except Exception as e:
        print(f"Upload failed: {e}")
        return {"status": "error", "message": f"Failed to upload file to S3: {str(e)}"}

    print("deleting file from disk..")
    if os.path.exists(target):
        os.remove(target)

    return {"status": "success", "s3_path": f"s3://{bucket_name}/{s3_key}"}

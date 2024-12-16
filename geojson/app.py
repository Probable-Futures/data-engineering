import os
import subprocess
import boto3


def lambda_handler(event, context):
    dataset_id = event.get("dataset_id")
    if not dataset_id:
        raise ValueError("Missing required parameter: dataset_id")

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

    target = f"/tmp/data/mapbox/mts/{dataset_id}.geojsonld"
    s3_key = f"climate-data/full-data-geojson/{dataset_id}.geojsonld"

    # Run gmake with the specified target
    try:
        subprocess.run(["gmake", target], check=True, env=env)
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": str(e)}

    print("copying to S3..")

    s3_client = boto3.client("s3")
    try:
        s3_client.upload_file(target, bucket_name, s3_key)
    except Exception as e:
        return {"status": "error", "message": f"Failed to upload file to S3: {str(e)}"}

    print("deleting file from disk..")
    if os.path.exists(target):
        os.remove(target)

    return {"status": "success", "s3_path": f"s3://{bucket_name}/{s3_key}"}

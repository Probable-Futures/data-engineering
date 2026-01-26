import * as aws from "@pulumi/aws";
import * as pulumi from "@pulumi/pulumi";
import { glueRole } from "../iam/glueRole";
import { config } from "../config";

const sourceBucket = config.s3BucketName;
const targetBucket = config.s3BucketName;
const scriptsBucket = config.s3BucketName;

const inputPath = `s3://${sourceBucket}/climate-data-full-model-raw`;
const outputPath = `s3://${targetBucket}/climate-data-full-model-raw-parquet/parquet-files`;

const glueScript = new aws.s3.BucketObject("climateEtlScript", {
  bucket: scriptsBucket,
  key: "glue/climate_etl.py",
  source: new pulumi.asset.FileAsset("glueScripts/climate_etl.py"),
});

export const climateEtlJob = new aws.glue.Job("climateEtlJob", {
  roleArn: glueRole.arn,

  glueVersion: "4.0",
  workerType: "G.2X",
  numberOfWorkers: 10,

  command: {
    name: "glueetl",
    pythonVersion: "3",
    scriptLocation: pulumi.interpolate`s3://${scriptsBucket}/${glueScript.key}`,
  },

  defaultArguments: {
    "--job-language": "python",
    "--enable-glue-datacatalog": "true",
    "--OUTPUT_PATH": outputPath,
    "--INPUT_PATH": inputPath,
  },

  timeout: 2880,
});

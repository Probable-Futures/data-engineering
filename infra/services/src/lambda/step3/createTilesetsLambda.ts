import * as child_process from "child_process";
import * as pulumi from "@pulumi/pulumi";
import * as aws from "@pulumi/aws";
import * as path from "path";

import { config } from "../../config";

const lambdaProjectPath = path.join(config.rootDir, "vector-tiles");
const createTilesetResource = `${config.stackName}-create-tileset`;

const lambdaRole = new aws.iam.Role(`${createTilesetResource}-role`, {
  assumeRolePolicy: aws.iam.assumeRolePolicyForPrincipal({
    Service: "lambda.amazonaws.com",
  }),
});

new aws.iam.RolePolicy(`${createTilesetResource}-s3-policy`, {
  role: lambdaRole.name,
  policy: {
    Version: "2012-10-17",
    Statement: [
      {
        Effect: "Allow",
        Action: ["s3:GetObject"],
        Resource: "arn:aws:s3:::global-pf-data-engineering/*",
      },
    ],
  },
});

new aws.iam.RolePolicy(`${createTilesetResource}-cloudwatch-policy`, {
  role: lambdaRole.name,
  policy: {
    Version: "2012-10-17",
    Statement: [
      {
        Sid: "VisualEditor0",
        Effect: "Allow",
        Action: ["logs:CreateLogStream", "logs:CreateLogGroup", "logs:PutLogEvents"],
        Resource: "*",
      },
    ],
  },
});

const environmentVariables = {
  MAPBOX_ACCESS_TOKEN: config.mapboxAccessToken,
  APP_ENV: config.stackName,
  S3_BUCKET_NAME: config.s3BucketName,
};

child_process.execSync("npm run build", { cwd: lambdaProjectPath, stdio: "inherit" });

const lambdaArchive = new pulumi.asset.AssetArchive({
  dist: new pulumi.asset.FileArchive(path.join(lambdaProjectPath, "dist")),
  node_modules: new pulumi.asset.FileArchive(path.join(lambdaProjectPath, "node_modules")),
  "lambdaHandler.mjs": new pulumi.asset.FileAsset(
    path.join(lambdaProjectPath, "lambdaHandler.mjs"),
  ),
});

const lambdaFunction = new aws.lambda.Function(`${createTilesetResource}-function`, {
  runtime: "nodejs20.x",
  role: lambdaRole.arn,
  handler: "lambdaHandler.handler",
  architectures: ["arm64"],
  code: lambdaArchive,
  timeout: 600,
  memorySize: 1024,
  ephemeralStorage: { size: 1024 },
  environment: {
    variables: environmentVariables,
  },
});

export const createTilesetFunction = lambdaFunction.name;

import * as aws from "@pulumi/aws";
import * as pulumi from "@pulumi/pulumi";

import { config } from "../../config";
import { createLambdaPackage } from "./step1Helper";

const importNetCDFResource = `${config.stackName}-import-netcdf`;

const lambdaRole = new aws.iam.Role(`${importNetCDFResource}-role`, {
  assumeRolePolicy: aws.iam.assumeRolePolicyForPrincipal({
    Service: "lambda.amazonaws.com",
  }),
});

new aws.iam.RolePolicy(`${importNetCDFResource}-role`, {
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
      {
        Effect: "Allow",
        Action: [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
        ],
        Resource: "*",
      },
      {
        Sid: "RDSDataServiceAccess",
        Effect: "Allow",
        Action: ["rds-data:ExecuteStatement"],
        Resource: "*",
      },
      {
        Effect: "Allow",
        Action: "ssm:GetParameter",
        Resource: `arn:aws:ssm:us-west-2:188081825159:parameter/${config.stackName}-rds-pfowner-password`,
      },
      {
        Effect: "Allow",
        Action: ["s3:*", "s3-object-lambda:*"],
        Resource: "arn:aws:s3:::global-pf-data-engineering/*",
      },
    ],
  },
});

const lambdaToRDSSG = new aws.ec2.SecurityGroup(`${importNetCDFResource}-sg`, {
  description: "Security group for Lambda to access RDS",
  egress: [
    {
      protocol: "tcp",
      fromPort: 5432,
      toPort: 5432,
      cidrBlocks: ["0.0.0.0/0"],
      securityGroups: [config.vpc.vpcPostgresSecurityGroupId],
    },
    {
      protocol: "-1", // All traffic
      fromPort: 0,
      toPort: 0,
      prefixListIds: [config.s3PrefixListId],
    },
  ],
  vpcId: config.vpc.id,
});

// Update RDS security group to allow inbound from Lambda SG
new aws.ec2.SecurityGroupRule(`${importNetCDFResource}-rds-inbound-from-lambda`, {
  type: "ingress",
  fromPort: 5432,
  toPort: 5432,
  protocol: "tcp",
  securityGroupId: config.vpc.vpcPostgresSecurityGroupId,
  sourceSecurityGroupId: lambdaToRDSSG.id,
});

const pgPassword = aws.ssm.getParameterOutput({
  name: `${config.stackName}-rds-pfowner-password`,
  withDecryption: true,
});

const lambdaZip = createLambdaPackage();

const bucket = new aws.s3.Bucket(`${importNetCDFResource}-bucket`);

const lambdaObject = new aws.s3.BucketObject("lambda-package", {
  bucket: bucket.id,
  source: new pulumi.asset.FileAsset(lambdaZip),
});

const lambdaFunction = new aws.lambda.Function(`${importNetCDFResource}-function`, {
  runtime: "python3.9",
  s3Bucket: bucket.bucket,
  s3Key: lambdaObject.key,
  role: lambdaRole.arn,
  handler: "lambdaHandler.lambda_handler",
  memorySize: 2048,
  timeout: 600,
  architectures: ["arm64"],
  ephemeralStorage: { size: 1024 },
  environment: {
    variables: {
      PG_DBNAME: config.pgDbName,
      PG_HOST: config.pgHost,
      PG_PASSWORD: pgPassword.apply((p) => p).value,
      PG_PORT: "5432",
      PG_USER: config.pgUser,
      S3_BUCKET_NAME: config.s3BucketName,
      RUN_ENV: config.stackName,
    },
  },
  vpcConfig: {
    securityGroupIds: [lambdaToRDSSG.id],
    subnetIds: config.vpc.isolatedSubnetIds,
  },
});

export const importNetCDFLambdaName = lambdaFunction.name;

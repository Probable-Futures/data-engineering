import * as aws from "@pulumi/aws";
import * as awsx from "@pulumi/awsx";
import * as path from "path";

import { config } from "../../config";

const geojsonProjectPath = path.join(config.rootDir, "geojson");
const createGeojsonResource = `${config.stackName}-create-geojson`;

const lambdaRole = new aws.iam.Role(`${createGeojsonResource}-role`, {
  assumeRolePolicy: aws.iam.assumeRolePolicyForPrincipal({
    Service: "lambda.amazonaws.com",
  }),
});

new aws.iam.RolePolicy(`${createGeojsonResource}-role`, {
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
        Condition: {
          StringEquals: {
            "rds-data:StatementType": "SELECT",
          },
        },
      },
      {
        Effect: "Allow",
        Action: ["s3:*", "s3-object-lambda:*"],
        Resource: "arn:aws:s3:::global-pf-data-engineering/*",
      },
      {
        Effect: "Allow",
        Action: "ssm:GetParameter",
        Resource: `arn:aws:ssm:us-west-2:188081825159:parameter/${config.stackName}-rds-pfowner-password`,
      },
    ],
  },
});

const lambdaToRDSSG = new aws.ec2.SecurityGroup(`${createGeojsonResource}-sg`, {
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
new aws.ec2.SecurityGroupRule(`${createGeojsonResource}-rds-inbound-from-lambda`, {
  type: "ingress",
  fromPort: 5432,
  toPort: 5432,
  protocol: "tcp",
  securityGroupId: config.vpc.vpcPostgresSecurityGroupId,
  sourceSecurityGroupId: lambdaToRDSSG.id,
});

const ecrRepo = new awsx.ecr.Repository(`${createGeojsonResource}-repo`, {
  imageScanningConfiguration: {
    scanOnPush: true,
  },
  lifecyclePolicy: {
    rules: [{ maximumAgeLimit: 14, tagStatus: "untagged" }],
  },
});

console.log(geojsonProjectPath + "/Dockerfile");

const dockerImage = new awsx.ecr.Image(`${createGeojsonResource}-image`, {
  repositoryUrl: ecrRepo.repository.repositoryUrl,
  context: geojsonProjectPath,
  args: {
    ENV: config.stackName,
  },
  platform: "linux/arm64",
});

dockerImage.imageUri.apply((uri) => console.log(`Docker image URI: ${uri}`));

const pgPassword = aws.ssm.getParameterOutput({
  name: `${config.stackName}-rds-pfowner-password`,
  withDecryption: true,
});

const geojsonLambda = new aws.lambda.Function(`${createGeojsonResource}-function`, {
  packageType: "Image",
  imageUri: dockerImage.imageUri.apply((uri) => uri),
  memorySize: 2048,
  timeout: 600,
  ephemeralStorage: { size: 1024 },
  architectures: ["arm64"],
  role: lambdaRole.arn,
  environment: {
    variables: {
      PG_DBNAME: config.pgDbName,
      PG_HOST: config.pgHost,
      PG_PASSWORD: pgPassword.apply((p) => p).value,
      PG_PORT: "5432",
      PG_USER: config.pgUser,
      S3_BUCKET_NAME: config.s3BucketName,
    },
  },
  vpcConfig: {
    securityGroupIds: [lambdaToRDSSG.id],
    subnetIds: config.vpc.isolatedSubnetIds,
  },
});

export const geojsonLambdaName = geojsonLambda.name;

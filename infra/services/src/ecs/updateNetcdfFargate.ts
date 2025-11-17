import * as aws from "@pulumi/aws";
import * as awsx from "@pulumi/awsx";
import * as path from "path";

import { config } from "../config";

const updateNetCDFResource = `${config.stackName}-update-netcdf`;
export const updateNetCDFPath = path.join(config.rootDir, "netcdfs", "import");

const ecrRepo = new awsx.ecr.Repository(`${updateNetCDFResource}-repo`, {
  imageScanningConfiguration: { scanOnPush: true },
  lifecyclePolicy: { rules: [{ maximumAgeLimit: 14, tagStatus: "untagged" }] },
});

const dockerImage = new awsx.ecr.Image(`${updateNetCDFResource}-image`, {
  repositoryUrl: ecrRepo.repository.repositoryUrl,
  context: updateNetCDFPath,
  args: { ENV: config.stackName },
  platform: "linux/arm64",
  dockerfile: path.join(updateNetCDFPath, "Dockerfile.update"),
  builderVersion: "BuilderBuildKit",
});

const ecsTaskRole = new aws.iam.Role(`${updateNetCDFResource}-task-role`, {
  assumeRolePolicy: aws.iam.assumeRolePolicyForPrincipal({
    Service: "ecs-tasks.amazonaws.com",
  }),
});

new aws.iam.RolePolicyAttachment(`${updateNetCDFResource}-task-execution`, {
  role: ecsTaskRole.name,
  policyArn: aws.iam.ManagedPolicy.AmazonECSTaskExecutionRolePolicy,
});

new aws.iam.RolePolicy(`${updateNetCDFResource}-custom-policy`, {
  role: ecsTaskRole.name,
  policy: {
    Version: "2012-10-17",
    Statement: [
      { Effect: "Allow", Action: ["logs:*"], Resource: "*" },
      {
        Effect: "Allow",
        Action: ["s3:*"],
        Resource: "arn:aws:s3:::global-pf-data-engineering/*",
      },
      {
        Effect: "Allow",
        Action: ["rds-data:*"],
        Resource: "*",
      },
      {
        Effect: "Allow",
        Action: ["ssm:GetParameter"],
        Resource: `arn:aws:ssm:us-west-2:188081825159:parameter/${config.stackName}-rds-pfowner-password`,
      },
    ],
  },
});

const logGroup = new aws.cloudwatch.LogGroup(`${updateNetCDFResource}-logs`, {
  retentionInDays: 14,
});

const pgPassword = aws.ssm.getParameterOutput({
  name: `${config.stackName}-rds-pfowner-password`,
  withDecryption: true,
});

const taskDefinition = new awsx.ecs.FargateTaskDefinition(`${updateNetCDFResource}-taskdef`, {
  container: {
    name: "update-netcdf",
    image: dockerImage.imageUri,
    cpu: 4096,
    memory: 8192,
    essential: true,
    environment: [
      { name: "PG_DBNAME", value: config.pgDbName },
      { name: "PG_HOST", value: config.pgHost },
      { name: "PG_USER", value: config.pgUser },
      { name: "PG_PASSWORD", value: pgPassword.value },
      { name: "S3_BUCKET_NAME", value: config.s3BucketName },
      { name: "RUN_ENV", value: config.stackName },
    ],
    logConfiguration: {
      logDriver: "awslogs",
      options: {
        "awslogs-group": logGroup.name,
        "awslogs-region": "us-west-2",
        "awslogs-stream-prefix": "fargate",
      },
    },
  },
  executionRole: { roleArn: ecsTaskRole.arn },
  taskRole: { roleArn: ecsTaskRole.arn },
  runtimePlatform: {
    cpuArchitecture: "ARM64",
    operatingSystemFamily: "LINUX",
  },
});

export const updateNetCDFTaskDefArn = taskDefinition.taskDefinition.arn;
export const updateNetCDFSubnetIds = config.vpc.isolatedSubnetIds;
export const updateNetCDFSecurityGroups = [config.vpc.vpcPostgresSecurityGroupId];

import * as aws from "@pulumi/aws";

export const glueRole = new aws.iam.Role("climateDataGlueRole", {
  assumeRolePolicy: aws.iam.assumeRolePolicyForPrincipal({
    Service: "glue.amazonaws.com",
  }),
});

new aws.iam.RolePolicyAttachment("glueServicePolicy", {
  role: glueRole.name,
  policyArn: aws.iam.ManagedPolicy.AWSGlueServiceRole,
});

new aws.iam.RolePolicyAttachment("glueS3Policy", {
  role: glueRole.name,
  policyArn: aws.iam.ManagedPolicy.AmazonS3FullAccess,
});

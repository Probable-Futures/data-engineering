import { join } from "path";
import * as pulumi from "@pulumi/pulumi";

import { createBaseConfig, BaseConfig } from "./utils";

const rootDir = join(__dirname, "..", "..", "..");
const baseConfig = createBaseConfig();
const { pulumiConfig, stackName } = baseConfig;

const foundationResources = new pulumi.StackReference(`Probable-Futures/foundation/${stackName}`);

interface ServicesConfig extends BaseConfig {
  mapboxAccessToken: pulumi.Output<string>;
  s3PrefixListId: pulumi.Output<string>;
  pgHost: pulumi.Output<string>;
  pgUser: pulumi.Output<string>;
  pgDbName: pulumi.Output<string>;
  s3BucketName: string;
  rootDir: string;
  vpc: {
    isolatedSubnetIds: pulumi.Output<any>;
    vpcPostgresSecurityGroupId: pulumi.Output<any>;
    id: pulumi.Output<any>;
  };
}

export const config: ServicesConfig = {
  rootDir,
  mapboxAccessToken: pulumiConfig.requireSecret("mapboxAccessToken"),
  s3BucketName: pulumiConfig.require("s3BucketName"),
  s3PrefixListId: pulumiConfig.requireSecret("s3PrefixListId"),
  pgHost: pulumiConfig.requireSecret("pgHost"),
  pgUser: pulumiConfig.requireSecret("pgUser"),
  pgDbName: pulumiConfig.requireSecret("pgDbName"),
  vpc: {
    isolatedSubnetIds: foundationResources.requireOutput("isolatedSubnetIds"),
    id: foundationResources.requireOutput("vpcId"),
    vpcPostgresSecurityGroupId: foundationResources.requireOutput("vpcPostgresSecurityGroupId"),
  },
  ...baseConfig,
};

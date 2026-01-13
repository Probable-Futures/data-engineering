import { join } from "path";

import { createBaseConfig, BaseConfig } from "./utils";

const rootDir = join(__dirname, "..", "..", "..");
const baseConfig = createBaseConfig();
const { pulumiConfig, stackName } = baseConfig;

interface GlobalConfig extends BaseConfig {
  s3BucketName: string;
  rootDir: string;
}

export const config: GlobalConfig = {
  rootDir,
  s3BucketName: pulumiConfig.require("s3BucketName"),
  ...baseConfig,
};

import { ECSClient, RunTaskCommand } from "@aws-sdk/client-ecs";

const ecs = new ECSClient({ region: "us-west-2" });

async function triggerUpdateNetCDF() {
  await ecs.send(
    new RunTaskCommand({
      cluster: process.env.UPDATE_NETCDF_CLUSTER_ARN!,
      taskDefinition: process.env.UPDATE_NETCDF_TASKDEF_ARN!,
      launchType: "FARGATE",
      networkConfiguration: {
        awsvpcConfiguration: {
          subnets: process.env.UPDATE_NETCDF_SUBNETS!.split(","),
          securityGroups: process.env.UPDATE_NETCDF_SECURITY_GROUPS!.split(","),
          assignPublicIp: "DISABLED",
        },
      },
      overrides: {
        containerOverrides: [
          {
            name: "update-netcdf",
            command: [
              "python",
              "pfupdate.py",
              "--load-one-cdf",
              "40101",
              "--netcdf-object-key",
              "climate-data/v3/heat/03_mosaicked/average-temperature_v03.nc",
            ],
          },
        ],
      },
    }),
  );
}

triggerUpdateNetCDF();

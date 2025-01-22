import * as fs from "fs";
import * as path from "path";
import * as childProcess from "child_process";

import { config } from "../../config";

const packageDir = path.join(config.rootDir, "netcdfs", "import");
const lambdaPackageDir = path.join(packageDir, "lambda_package");

export function createLambdaPackage(): string {
  // Clean up any existing package directory
  if (fs.existsSync(lambdaPackageDir)) {
    fs.rmdirSync(lambdaPackageDir, { recursive: true });
  }
  fs.mkdirSync(lambdaPackageDir);

  // Install dependencies into the package directory
  console.log("Installing dependencies...");
  childProcess.execSync(`pip install -r requirements.txt -t ${lambdaPackageDir}/python`, {
    stdio: "inherit",
    cwd: packageDir,
  });

  // Copy project files to the package directory
  fs.copyFileSync(path.join(packageDir, "pfimport.py"), path.join(lambdaPackageDir, "pfimport.py"));
  fs.copyFileSync(path.join(packageDir, "conf.yaml"), path.join(lambdaPackageDir, "conf.yaml"));
  fs.copyFileSync(path.join(packageDir, "helpers.py"), path.join(lambdaPackageDir, "helpers.py"));
  fs.copyFileSync(
    path.join(packageDir, "lambdaHandler.py"),
    path.join(lambdaPackageDir, "lambdaHandler.py"),
  );
  fs.copyFileSync(
    path.join(packageDir, "pfimport-new.py"),
    path.join(lambdaPackageDir, "pfimport-new.py"),
  );
  fs.copyFileSync(path.join(packageDir, "pfupdate.py"), path.join(lambdaPackageDir, "pfupdate.py"));

  // Copy the entire 'util' folder to the package directory
  const utilDir = path.join(packageDir, "util");
  const targetUtilDir = path.join(lambdaPackageDir, "util");

  copyFolderSync(utilDir, targetUtilDir);

  // Zip the package
  const zipFile = `${lambdaPackageDir}.zip`;
  if (fs.existsSync(zipFile)) {
    fs.unlinkSync(zipFile);
  }
  console.log("Zipping package...");
  childProcess.execSync(`zip -r ${zipFile} .`, {
    cwd: lambdaPackageDir,
    stdio: "inherit",
  });

  return zipFile;
}

function copyFolderSync(source: string, target: string) {
  if (!fs.existsSync(target)) {
    fs.mkdirSync(target);
  }

  const entries = fs.readdirSync(source, { withFileTypes: true });

  for (const entry of entries) {
    const sourcePath = path.join(source, entry.name);
    const targetPath = path.join(target, entry.name);

    if (entry.isDirectory()) {
      copyFolderSync(sourcePath, targetPath);
    } else {
      fs.copyFileSync(sourcePath, targetPath);
    }
  }
}

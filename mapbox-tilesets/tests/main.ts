import "dotenv/config";

import { start } from "./index";

export default async function main(): Promise<void> {
  start();
}

main().catch((e) => {});

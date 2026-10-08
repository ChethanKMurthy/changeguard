import { Logger } from "../log/logger";

export function boot(): string {
  const logger = new Logger("app");
  return logger.info("booted");
}

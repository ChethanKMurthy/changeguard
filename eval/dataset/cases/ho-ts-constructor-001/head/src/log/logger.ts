export class Logger {
  constructor(private name: string, private level: "debug" | "info") {}

  info(message: string): string {
    return this.level === "info" ? `[${this.name}] ${message}` : "";
  }
}

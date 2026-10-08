export class Logger {
  constructor(private name: string) {}

  info(message: string): string {
    return `[${this.name}] ${message}`;
  }
}

export class LruCache<V> {
  private items = new Map<string, V>();

  constructor(private capacity: number) {}

  get(key: string): V | undefined {
    return this.items.get(key);
  }

  set(key: string, value: V): void {
    this.items.delete(key);
    this.items.set(key, value);
    this.evict();
  }

  evict(): void {
    while (this.items.size > this.capacity) {
      const oldest = this.items.keys().next().value as string;
      this.items.delete(oldest);
    }
  }
}

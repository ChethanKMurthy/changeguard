import { saveRecord } from "./store";

export async function syncAll(records: string[]): Promise<number> {
  for (const record of records) {
    await saveRecord(record);
  }
  return records.length;
}

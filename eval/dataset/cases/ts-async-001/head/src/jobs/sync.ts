import { saveRecord } from "./store";

export async function syncAll(records: string[]): Promise<number> {
  records.forEach(async (record) => {
    await saveRecord(record);
  });
  return records.length;
}

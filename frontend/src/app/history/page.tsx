import type { Metadata } from "next";

import { HistoryList } from "./history-list";

export const metadata: Metadata = {
  title: "Reports",
  description: "Analyses run from this browser, newest first, with their findings and exports.",
};

export default function HistoryPage() {
  return <HistoryList />;
}

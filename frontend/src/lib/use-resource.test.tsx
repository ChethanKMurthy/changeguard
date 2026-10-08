import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { invalidate, useResource } from "./use-resource";

function Reader({ name, fetcher, k }: { name: string; fetcher: () => Promise<string>; k: string }) {
  const { data, loading } = useResource(k, fetcher, { maxAgeMs: 60_000 });
  return <p data-testid={name}>{loading ? "loading" : data}</p>;
}

describe("useResource", () => {
  it("shares one request between components reading the same key", async () => {
    const fetcher = vi.fn(async () => "value");
    render(
      <>
        <Reader name="a" k="shared-key" fetcher={fetcher} />
        <Reader name="b" k="shared-key" fetcher={fetcher} />
      </>,
    );
    await waitFor(() => expect(screen.getByTestId("a")).toHaveTextContent("value"));
    expect(screen.getByTestId("b")).toHaveTextContent("value");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("keeps showing data after invalidation until the refetch lands", async () => {
    let n = 0;
    const fetcher = vi.fn(async () => `v${++n}`);
    const { unmount } = render(<Reader name="c" k="stale-key" fetcher={fetcher} />);
    await waitFor(() => expect(screen.getByTestId("c")).toHaveTextContent("v1"));
    invalidate("stale-");
    expect(screen.getByTestId("c")).toHaveTextContent("v1");
    unmount();
    render(<Reader name="c" k="stale-key" fetcher={fetcher} />);
    await waitFor(() => expect(screen.getByTestId("c")).toHaveTextContent("v2"));
  });

  it("reports errors without throwing", async () => {
    function Failing() {
      const { error, loading } = useResource("failing-key", async () => {
        throw new Error("boom");
      });
      return <p data-testid="f">{loading ? "loading" : error ? error.message : "ok"}</p>;
    }
    render(<Failing />);
    await waitFor(() => expect(screen.getByTestId("f")).toHaveTextContent("boom"));
  });
});

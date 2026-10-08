"use client";

import { useEffect } from "react";

import { Button, ButtonLink } from "@/components/ui/button";

/** Route-level error boundary: shows what happened without exposing internals, and offers a retry. */
export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto grid min-h-[60vh] max-w-[1240px] items-center px-4 py-20 sm:px-6">
      <div className="max-w-xl" role="alert">
        <p className="font-mono text-[0.6875rem] text-muted">
          error{error.digest ? ` · digest ${error.digest}` : ""}
        </p>
        <h1 className="display mt-4 text-[clamp(2.2rem,4.4vw,3.4rem)]">This page failed to render.</h1>
        <p className="prose-lab mt-5">
          Something went wrong while building this view. Nothing was lost: reports live in the engine, not in this page. Try
          again, or go back to the reports list.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button onClick={reset}>Try again</Button>
          <ButtonLink href="/history" variant="secondary">
            All reports
          </ButtonLink>
        </div>
      </div>
    </div>
  );
}

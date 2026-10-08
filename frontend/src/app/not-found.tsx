import type { Metadata } from "next";

import { ButtonLink } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Not found",
};

export default function NotFound() {
  return (
    <div className="mx-auto grid min-h-[60vh] max-w-[1240px] items-center px-4 py-20 sm:px-6">
      <div className="max-w-xl">
        <p className="font-mono text-[0.6875rem] text-muted">404 · no evidence at this path</p>
        <h1 className="display mt-4 text-[clamp(2.2rem,4.4vw,3.4rem)]">Nothing here to analyse.</h1>
        <p className="prose-lab mt-5">
          The page you asked for does not exist. If you followed a link to a report, it may have been deleted, or the engine
          may have started with a fresh database.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <ButtonLink href="/">Home</ButtonLink>
          <ButtonLink href="/history" variant="secondary">
            All reports
          </ButtonLink>
          <ButtonLink href="/experience" variant="ghost">
            Guided experience
          </ButtonLink>
        </div>
      </div>
    </div>
  );
}

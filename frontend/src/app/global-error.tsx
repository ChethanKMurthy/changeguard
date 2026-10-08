"use client";

/**
 * Last-resort boundary for errors in the root layout itself. It replaces the
 * whole document, so it carries its own minimal markup and inline styles.
 */
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "ui-sans-serif, system-ui, sans-serif", background: "#fff", color: "#1c1917" }}>
        <main style={{ maxWidth: 560, margin: "18vh auto", padding: "0 20px" }}>
          <p style={{ fontFamily: "ui-monospace, monospace", fontSize: 12, color: "#57534e" }}>ChangeGuard</p>
          <h1 style={{ fontSize: 32, lineHeight: 1.15, margin: "12px 0" }}>The application failed to load.</h1>
          <p style={{ fontSize: 16, lineHeight: 1.6, color: "#44403c" }}>
            Reload the page to try again. If this keeps happening, check that the engine is running and reachable.
          </p>
          <button
            type="button"
            onClick={reset}
            style={{ marginTop: 20, height: 40, padding: "0 16px", borderRadius: 6, border: 0, background: "#1c1917", color: "#fff", fontSize: 14, cursor: "pointer" }}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}

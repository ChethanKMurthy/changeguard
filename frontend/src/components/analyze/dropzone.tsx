"use client";

import { useId, useRef, useState } from "react";

import { cn } from "@/lib/cn";

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function Dropzone({
  label,
  hint,
  accept,
  file,
  onFile,
  maxBytes,
  icon,
}: {
  label: string;
  hint: React.ReactNode;
  accept: string;
  file: File | null;
  onFile: (file: File | null) => void;
  maxBytes?: number;
  icon?: React.ReactNode;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const tooLarge = Boolean(file && maxBytes && file.size > maxBytes);

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-sm font-medium text-ink">
          {label}
        </label>
        {maxBytes && <span className="font-mono text-[0.6875rem] text-faint">max {formatBytes(maxBytes)}</span>}
      </div>
      {file ? (
        <div className={cn("flex items-center gap-3 rounded-[10px] border px-3.5 py-3", tooLarge ? "border-danger/50 bg-danger-tint" : "border-line bg-surface")}>
          <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-line bg-bg text-muted" aria-hidden="true">
            {icon ?? <FileIcon />}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-mono text-[0.8125rem] text-ink">{file.name}</span>
            <span className={cn("text-xs", tooLarge ? "text-danger" : "text-muted")}>
              {formatBytes(file.size)}
              {tooLarge && maxBytes ? ` — over the ${formatBytes(maxBytes)} limit` : ""}
            </span>
          </span>
          <button
            type="button"
            className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-ink"
            onClick={() => {
              onFile(null);
              if (input.current) input.current.value = "";
            }}
          >
            Remove
          </button>
        </div>
      ) : (
        <label
          htmlFor={id}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const dropped = e.dataTransfer.files?.[0];
            if (dropped) onFile(dropped);
          }}
          className={cn(
            "flex cursor-pointer items-center gap-3 rounded-[10px] border border-dashed px-3.5 py-3.5 transition-colors duration-150",
            dragging ? "border-signal bg-signal-tint" : "border-line-strong hover:border-ink/50 hover:bg-surface",
          )}
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-line bg-bg text-muted" aria-hidden="true">
            {icon ?? <FileIcon />}
          </span>
          <span className="min-w-0 text-[0.8125rem] leading-snug text-muted">
            <span className="font-medium text-ink">Choose a file</span> or drop it here
            <span className="mt-0.5 block text-xs">{hint}</span>
          </span>
        </label>
      )}
      <input
        ref={input}
        id={id}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
    </div>
  );
}

function FileIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4" aria-hidden="true">
      <path d="M4 1.5h5.5L13 5v9.5H4z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M9.5 1.5V5H13" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  );
}

export function ArchiveIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4" aria-hidden="true">
      <rect x="2" y="2.5" width="12" height="11" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path d="M2 6h12M6.5 8.5h3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

export function GaugeIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4" aria-hidden="true">
      <path d="M2.5 11a5.5 5.5 0 1 1 11 0" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      <path d="M8 11 10.5 7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

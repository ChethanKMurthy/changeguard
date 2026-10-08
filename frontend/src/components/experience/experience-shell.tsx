"use client";

import { motion, useReducedMotion, useScroll, useSpring } from "motion/react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

export interface ChapterLink {
  id: string;
  n: string;
  title: string;
  time?: string | null;
}

/**
 * Two-column reading layout. The rail is the pipeline itself: its trace fills
 * as the reader moves through the chapters, the way a change moves through the stages.
 */
export function ExperienceShell({
  chapters,
  children,
  heading = "Pipeline, chapter by chapter",
}: {
  chapters: ChapterLink[];
  children: ReactNode;
  heading?: string;
}) {
  const reduce = useReducedMotion();
  const articleRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: articleRef, offset: ["start 40%", "end 60%"] });
  const smooth = useSpring(scrollYProgress, { stiffness: 260, damping: 42, restDelta: 0.001 });
  const progress = reduce ? scrollYProgress : smooth;
  const [active, setActive] = useState(chapters[0]?.id);

  useEffect(() => {
    const sections = chapters.map((c) => document.getElementById(c.id)).filter((el): el is HTMLElement => Boolean(el));
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-38% 0px -58% 0px" },
    );
    sections.forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, [chapters]);

  const activeIndex = Math.max(
    0,
    chapters.findIndex((c) => c.id === active),
  );
  const current = chapters[activeIndex];

  return (
    <div className="mx-auto grid max-w-[1240px] grid-cols-1 px-4 sm:px-6 lg:grid-cols-[216px_minmax(0,1fr)] lg:gap-14">
      <aside className="hidden lg:block" aria-label="Chapters">
        <nav className="sticky top-24 py-2">
          <p className="mb-3 text-[0.6875rem] font-medium text-muted">{heading}</p>
          <div className="relative">
            <span className="absolute bottom-2 left-[8.5px] top-2 w-px bg-line" aria-hidden="true" />
            <motion.span
              className="absolute left-[8px] top-2 w-[2px] origin-top rounded-full bg-signal-glow"
              style={{ height: "calc(100% - 1rem)", scaleY: progress }}
              aria-hidden="true"
            />
            <ol className="relative space-y-0.5">
              {chapters.map((chapter, i) => {
                const state = i < activeIndex ? "done" : i === activeIndex ? "active" : "next";
                return (
                  <li key={chapter.id}>
                    <a
                      href={`#${chapter.id}`}
                      aria-current={state === "active" ? "location" : undefined}
                      className="group grid grid-cols-[18px_minmax(0,1fr)] items-start gap-3 rounded-md py-1.5 pr-2"
                    >
                      <span
                        className={cn(
                          "relative z-10 mt-[2px] flex size-[18px] items-center justify-center rounded-[5px] border font-mono text-[0.5625rem] font-semibold transition-colors duration-200",
                          state === "done" && "border-ink bg-ink text-bg",
                          state === "active" && "border-signal bg-signal-tint text-signal",
                          state === "next" && "border-line-strong bg-bg text-faint",
                        )}
                        aria-hidden="true"
                      >
                        {chapter.n}
                      </span>
                      <span className="min-w-0">
                        <span
                          className={cn(
                            "block text-[0.8125rem] leading-snug transition-colors duration-200",
                            state === "active" ? "font-semibold text-ink" : state === "done" ? "text-ink-soft group-hover:text-ink" : "text-muted group-hover:text-ink",
                          )}
                        >
                          {chapter.title}
                        </span>
                        {chapter.time && <span className="block font-mono text-[0.625rem] text-faint numeric">{chapter.time}</span>}
                      </span>
                    </a>
                  </li>
                );
              })}
            </ol>
          </div>
        </nav>
      </aside>

      <div ref={articleRef} className="min-w-0">
        {/* Compact progress for small screens */}
        <div className="sticky top-16 z-20 -mx-4 border-b border-line bg-bg px-4 sm:-mx-6 sm:px-6 lg:hidden">
          <div className="flex h-10 items-center justify-between gap-3 text-[0.75rem]">
            <span className="min-w-0 truncate">
              <span className="font-mono text-signal">{current?.n}</span>
              <span className="text-faint"> / {chapters.length.toString().padStart(2, "0")}</span>
              <span className="ml-2 font-medium text-ink">{current?.title}</span>
            </span>
            {current?.time && <span className="shrink-0 font-mono text-[0.625rem] text-faint">{current.time}</span>}
          </div>
          <motion.span className="absolute inset-x-0 bottom-[-1px] h-[2px] origin-left bg-signal-glow" style={{ scaleX: progress }} aria-hidden="true" />
        </div>
        {children}
      </div>
    </div>
  );
}

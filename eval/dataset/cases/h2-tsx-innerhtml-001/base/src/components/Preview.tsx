import { useEffect, useRef } from "react";

export function Preview({ markdown }: { markdown: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.textContent = markdown;
  }, [markdown]);
  return <div ref={ref} />;
}

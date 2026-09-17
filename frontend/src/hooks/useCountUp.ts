import { useEffect, useRef, useState } from "react";

const NUMERIC_PREFIX = /^(-?[\d.]+)(.*)$/;

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

export function useCountUp<T extends HTMLElement>(value: string, durationMs = 1200) {
  const match = value.match(NUMERIC_PREFIX);
  const target = match ? Number.parseFloat(match[1]) : null;
  const suffix = match ? match[2] : "";
  const decimals = match && match[1].includes(".") ? match[1].split(".")[1].length : 0;

  const [display, setDisplay] = useState(value);
  const ref = useRef<T | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (target === null) {
      return;
    }

    if (typeof IntersectionObserver === "undefined" || prefersReducedMotion() || !ref.current) {
      setDisplay(value);
      return;
    }

    const element = ref.current;
    const targetValue = target;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || started.current) {
          return;
        }
        started.current = true;

        const start = performance.now();

        function tick(now: number) {
          const progress = Math.min((now - start) / durationMs, 1);
          const eased = 1 - (1 - progress) ** 3;
          setDisplay(`${(targetValue * eased).toFixed(decimals)}${suffix}`);

          if (progress < 1) {
            requestAnimationFrame(tick);
          }
        }

        requestAnimationFrame(tick);
      },
      { threshold: 0.4 },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [target, suffix, decimals, durationMs, value]);

  return { ref, display };
}

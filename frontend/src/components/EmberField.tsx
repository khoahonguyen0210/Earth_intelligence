import { useMemo } from "react";

interface Ember {
  left: string;
  size: string;
  duration: string;
  delay: string;
  drift: string;
  peak: number;
}

function randomEmber(): Ember {
  return {
    left: `${Math.random() * 100}%`,
    size: `${2 + Math.random() * 3}px`,
    duration: `${5 + Math.random() * 5}s`,
    delay: `${Math.random() * 8}s`,
    drift: `${Math.round((Math.random() - 0.5) * 60)}px`,
    peak: 0.5 + Math.random() * 0.4,
  };
}

export function EmberField({ count = 14 }: { count?: number }) {
  const embers = useMemo(() => Array.from({ length: count }, randomEmber), [count]);

  return (
    <div className="ember-field" aria-hidden="true">
      {embers.map((ember, index) => (
        <span
          key={index}
          className="ember"
          style={{
            left: ember.left,
            "--ember-size": ember.size,
            "--ember-duration": ember.duration,
            "--ember-delay": ember.delay,
            "--ember-drift": ember.drift,
            "--ember-peak": ember.peak,
          } as React.CSSProperties}
        />
      ))}
    </div>
  );
}

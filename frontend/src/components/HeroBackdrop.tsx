const CLOUDS = [
  { top: "6%", width: 620, height: 170, opacity: 0.35, duration: 120, delay: -20 },
  { top: "18%", width: 820, height: 210, opacity: 0.28, duration: 160, delay: -90 },
  { top: "34%", width: 560, height: 150, opacity: 0.33, duration: 130, delay: -50 },
  { top: "50%", width: 900, height: 240, opacity: 0.24, duration: 190, delay: -140 },
  { top: "66%", width: 700, height: 190, opacity: 0.31, duration: 150, delay: -10 },
  { top: "82%", width: 960, height: 260, opacity: 0.27, duration: 210, delay: -110 },
];

export function HeroBackdrop() {
  return (
    <div className="sky" aria-hidden="true">
      <div className="sky-glow" />
      {CLOUDS.map((cloud) => (
        <span
          key={cloud.top}
          className="sky-cloud"
          style={{
            top: cloud.top,
            width: cloud.width,
            height: cloud.height,
            opacity: cloud.opacity,
            animationDuration: `${cloud.duration}s`,
            animationDelay: `${cloud.delay}s`,
          }}
        />
      ))}
    </div>
  );
}

/** Section 9.6: semi-circular SLA compliance gauge with tick marks. */
export function Gauge({ percent, label }: { percent: number; label: string }) {
  const clamped = Math.max(0, Math.min(100, percent));
  const angle = (clamped / 100) * 180;
  const r = 70;
  const cx = 90;
  const cy = 90;
  const needleRad = ((180 - angle) * Math.PI) / 180;
  const nx = cx + r * Math.cos(needleRad);
  const ny = cy - r * Math.sin(needleRad);
  const ticks = Array.from({ length: 11 }, (_, i) => i * 18);

  return (
    <div role="img" aria-label={`${label}: ${clamped.toFixed(0)} percent`} className="flex flex-col items-center">
      <svg width="180" height="100" viewBox="0 0 180 100">
        <defs>
          <linearGradient id="gaugeGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#1787C7" />
            <stop offset="55%" stopColor="#3DA7E3" />
            <stop offset="100%" stopColor="#55BFFD" />
          </linearGradient>
        </defs>
        <path d="M 20 90 A 70 70 0 0 1 160 90" fill="none" stroke="var(--color-brand-50)" strokeWidth="10" />
        <path
          d={`M 20 90 A 70 70 0 0 1 ${nx.toFixed(1)} ${ny.toFixed(1)}`}
          fill="none"
          stroke="url(#gaugeGrad)"
          strokeWidth="10"
          strokeLinecap="round"
        />
        {ticks.map((deg) => {
          const rad = ((180 - deg) * Math.PI) / 180;
          const x1 = cx + (r - 6) * Math.cos(rad);
          const y1 = cy - (r - 6) * Math.sin(rad);
          const x2 = cx + (r + 2) * Math.cos(rad);
          const y2 = cy - (r + 2) * Math.sin(rad);
          return (
            <line key={deg} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--color-outline)" strokeWidth="2" />
          );
        })}
        <circle cx={nx} cy={ny} r="5" fill="var(--color-brand-500)" />
      </svg>
      <div className="text-2xl font-semibold tabular-nums text-ink">{clamped.toFixed(0)}%</div>
      <div className="text-sm text-ink-muted">{label}</div>
    </div>
  );
}

import { t } from "../../styles/tokens";

interface SparklineProps {
  data: number[];
  color?: string;
}

export function Sparkline({ data, color }: SparklineProps) {
  const w = 64;
  const h = 16;
  const s = w / data.length;

  return (
    <svg width={w} height={h} className="shrink-0">
      {data.map((v, i) => (
        <rect
          key={i}
          x={i * s + 1}
          y={h - v * h}
          width={s - 2}
          height={Math.max(1, v * h)}
          rx={1}
          fill={v >= 1 ? color || t.green : v >= 0.5 ? t.amber : t.red}
          opacity={0.8}
        />
      ))}
    </svg>
  );
}

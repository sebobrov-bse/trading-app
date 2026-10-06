import { createChart, LineSeries } from 'lightweight-charts';
import type { IChartApi } from 'lightweight-charts';
import { useEffect, useRef } from 'react';
import type { BacktestForCompare } from '../api/types';

interface CompareEquityChartProps {
  backtests: BacktestForCompare[];
  height?: number;
}

const COLORS = ['#2962FF', '#FF6D00', '#00C853', '#AA00FF', '#D50000'];

export function CompareEquityChart({
  backtests,
  height = 500,
}: CompareEquityChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height,
      layout: { background: { color: '#ffffff' }, textColor: '#374151' },
      grid: {
        vertLines: { color: '#f3f4f6' },
        horzLines: { color: '#f3f4f6' },
      },
      timeScale: { borderColor: '#e5e7eb' },
      rightPriceScale: { borderColor: '#e5e7eb' },
    });

    backtests.forEach((bt, i) => {
      const series = chart.addSeries(LineSeries, {
        color: COLORS[i % COLORS.length],
        lineWidth: 2,
      });
      series.setData(
        bt.equity_curve.map((p) => ({
          time: p.timestamp.slice(0, 10),
          value: p.value,
        })),
      );
    });

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const resizeObserver = new ResizeObserver(() => {
      chart.applyOptions({ width: container.clientWidth });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [backtests, height]);

  return (
    <>
      <div ref={containerRef} className="equity-chart" />
      <div className="chart-legend">
        {backtests.map((bt, i) => (
          <div key={bt.id} className="legend-item">
            <span
              className="legend-marker"
              style={{ background: COLORS[i % COLORS.length] }}
            />
            #{bt.id} {bt.strategy}
          </div>
        ))}
      </div>
    </>
  );
}
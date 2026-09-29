import { createChart, LineSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { useEffect, useRef } from 'react';
import type { EquityPoint } from '../api/types';

interface EquityChartProps {
  data: EquityPoint[];
  height?: number;
}

export function EquityChart({ data, height = 400 }: EquityChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null);

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

    // v5 API: addSeries(SeriesDefinition, options)
    const series = chart.addSeries(LineSeries, {
      color: '#2962FF',
      lineWidth: 2,
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const resizeObserver = new ResizeObserver(() => {
      chart.applyOptions({ width: container.clientWidth });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    if (!seriesRef.current || data.length === 0) return;
    const points = data.map((p) => ({
      time: p.timestamp.slice(0, 10),
      value: p.value,
    }));
    seriesRef.current.setData(points);
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return <div ref={containerRef} className="equity-chart" />;
}
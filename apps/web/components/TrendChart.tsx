"use client";
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

export type Point = { label: string; value: number };

export function TrendChart({ points, summary }: { points: Point[]; summary: string }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!el.current) return;
    const chart = echarts.init(el.current, undefined, { renderer: "canvas" });
    const draw = () => {
      const css = getComputedStyle(document.documentElement);
      const v = (n: string) => css.getPropertyValue(n).trim();
      chart.setOption({
        animation: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
        grid: { left: 44, right: 24, top: 32, bottom: 40 },
        tooltip: { trigger: "axis", valueFormatter: (x: number) => `${x.toFixed(1)}%` },
        xAxis: { type: "category", data: points.map((p) => p.label), axisLabel: { color: v("--mu"), interval: 0, width: 110, overflow: "break" }, axisLine: { lineStyle: { color: v("--bd") } } },
        yAxis: { type: "value", min: 0, max: 100, axisLabel: { color: v("--mu"), formatter: "{value}%" }, splitLine: { lineStyle: { color: v("--bd") } } },
        series: [{ type: "line", data: points.map((p) => +(p.value * 100).toFixed(1)), symbolSize: 9, lineStyle: { color: v("--ac"), width: 2.5 },
          itemStyle: { color: v("--sf"), borderColor: v("--ac"), borderWidth: 2.5 }, label: { show: true, color: v("--tx"), formatter: "{c}%", position: "top" } }],
      });
    };
    draw();
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el.current);
    const mo = new MutationObserver(draw); // follow the light/dark toggle
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { ro.disconnect(); mo.disconnect(); chart.dispose(); };
  }, [points]);
  return <div ref={el} role="img" aria-label={summary} style={{ height: 240, padding: "0 12px" }} />;
}

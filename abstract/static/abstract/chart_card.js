import * as echarts from "https://esm.sh/echarts@5.6.0";
import escapeHtml from "https://esm.sh/lodash.escape@4.0.1";

import { toRgba } from "./chart.js";

function capitalize(text) {
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}

function axisMax(percent, threshold) {
  return (value) => {
    const highest = Math.max(
      Number.isFinite(value.max) ? value.max : 0,
      threshold,
    );
    // A ceiling would round a 0.1 per cent limit up to a whole one.
    return percent ? highest * 1.1 : Math.ceil(highest * 1.05);
  };
}

function markLine(threshold, diverging) {
  if (threshold) {
    return {
      silent: true,
      symbol: "none",
      label: {
        show: true,
        position: "insideEndTop",
        formatter: threshold.label,
        color: toRgba("var(--color-muted-foreground)"),
      },
      lineStyle: {
        color: toRgba("var(--color-chart-gray)"),
        width: 2,
        type: "dashed",
      },
      data: [{ yAxis: threshold.value }],
    };
  }
  if (diverging) {
    return {
      silent: true,
      symbol: "none",
      label: { show: false },
      lineStyle: {
        color: toRgba("var(--color-muted-foreground)"),
        width: 2,
        type: "solid",
      },
      data: [{ yAxis: 0 }],
    };
  }
  return null;
}

function buildOption(payload, scale) {
  const { rows, series: seriesList, threshold } = payload;
  const locale = document.documentElement.lang;
  const fullDate = new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
  const shortDate = new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
  const muted = toRgba("var(--color-muted-foreground)");
  const border = toRgba("var(--color-border)");

  function formatValue(value) {
    return value === null || value === undefined
      ? "-"
      : String(scale.diverging ? Math.abs(value) : value);
  }

  const line = markLine(threshold, scale.diverging);
  return {
    grid: { left: 8, right: 16, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      confine: true,
      formatter: (items) =>
        [
          escapeHtml(fullDate.format(new Date(items[0].axisValue))),
          ...items.map((item) => {
            const text = formatValue(item.value);
            return `${item.marker}${escapeHtml(item.seriesName)}: ${escapeHtml(text)}${scale.percent && text !== "-" ? "%" : ""}`;
          }),
        ].join("<br/>"),
    },
    xAxis: {
      type: "category",
      data: rows.map((row) => row.day),
      axisLabel: {
        interval: Math.max(Math.ceil(rows.length / 6) - 1, 0),
        formatter: (value) => shortDate.format(new Date(value)),
      },
    },
    yAxis: {
      min: scale.diverging ? undefined : 0,
      axisLabel: scale.diverging
        ? { formatter: (value) => Math.abs(value) }
        : scale.percent
          ? { formatter: (value) => `${value}%` }
          : undefined,
      splitNumber: scale.percent ? 4 : undefined,
      max: threshold ? axisMax(scale.percent, threshold.value) : undefined,
    },
    series: seriesList.map((series, index) => ({
      name: capitalize(series.label),
      type: series.type ?? "bar",
      stack: scale.stacked ? "status" : undefined,
      showSymbol: false,
      lineStyle: { color: toRgba(series.color) },
      itemStyle: { color: toRgba(series.color) },
      data: rows.map((row) => row[series.key]),
      markLine: index === 0 && line ? line : undefined,
    })),
  };
}

function drawVariation(chart, rows, styles) {
  const barData = chart.getModel().getSeriesByIndex(0)?.getData();
  if (!barData) return;

  function pixelY(day, value) {
    return chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [day, value])[1];
  }

  const elements = [];
  for (let day = 1; day < rows.length; day += 1) {
    const left = barData.getItemLayout(day - 1);
    const right = barData.getItemLayout(day);
    if (!left || !right) return;
    // ECharts stacks the two directions away from zero, so a segment that
    // hangs below the axis needs the running base of the negative side.
    let leftUp = 0;
    let leftDown = 0;
    let rightUp = 0;
    let rightDown = 0;
    for (const { key, color } of styles) {
      const leftValue = rows[day - 1][key];
      const rightValue = rows[day][key];
      const leftBase = leftValue < 0 ? leftDown : leftUp;
      const rightBase = rightValue < 0 ? rightDown : rightUp;
      if (leftValue || rightValue) {
        elements.push({
          type: "polygon",
          silent: true,
          shape: {
            points: [
              [left.x + left.width, pixelY(day - 1, leftBase)],
              [left.x + left.width, pixelY(day - 1, leftBase + leftValue)],
              [right.x, pixelY(day, rightBase + rightValue)],
              [right.x, pixelY(day, rightBase)],
            ],
          },
          style: { fill: color, opacity: 0.25 },
        });
      }
      if (leftValue < 0) leftDown += leftValue;
      else leftUp += leftValue;
      if (rightValue < 0) rightDown += rightValue;
      else rightUp += rightValue;
    }
  }
  chart.setOption({ graphic: { elements } }, { replaceMerge: ["graphic"] });
}

function renderChart(element, payload) {
  const { y_scale: yScale = {} } = payload;
  const scale = {
    percent: yScale.percent === true,
    diverging: yScale.diverging === true,
    stacked: yScale.stacked !== false,
  };
  const styles = payload.series.map((series) => ({
    key: series.key,
    color: toRgba(series.color),
  }));
  const chart = echarts.init(element, "relay");
  chart.setOption(buildOption(payload, scale));
  function redraw() {
    chart.resize();
    if (scale.stacked) drawVariation(chart, payload.rows, styles);
  }

  redraw();
  globalThis.addEventListener("resize", redraw);
}

echarts.registerTheme("relay", {
  textStyle: {
    fontFamily: getComputedStyle(document.documentElement).fontFamily,
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: toRgba("var(--color-border)") } },
    axisTick: { show: false },
    axisLabel: { color: toRgba("var(--color-muted-foreground)") },
  },
  valueAxis: {
    axisLabel: { color: toRgba("var(--color-muted-foreground)") },
    splitLine: {
      lineStyle: { color: toRgba("var(--color-border)") },
    },
  },
  tooltip: {
    backgroundColor: toRgba("var(--color-popover)"),
    borderColor: toRgba("var(--color-border)"),
    textStyle: { color: toRgba("var(--color-popover-foreground)") },
  },
});

for (const element of document.querySelectorAll("[data-chart]")) {
  const source = document.getElementById(element.dataset.chart);
  if (source) renderChart(element, JSON.parse(source.textContent));
}

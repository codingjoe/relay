import * as echarts from "https://esm.sh/echarts@5.6.0";
import escapeHtml from "https://esm.sh/lodash.escape@4.0.1";

import { toRgba } from "../abstract/chart.js";

const element = document.getElementById("transmission-profile");
const source = document.getElementById("transmission-timeline");
const events = source ? JSON.parse(source.textContent) : [];

if (element && events.length) {
  const { duration, score, antivirus, transcript: hint } = element.dataset;
  const locale = document.documentElement.lang || "en";
  const msFormat = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  const secondFormat = new Intl.NumberFormat(locale, {
    maximumFractionDigits: 2,
  });
  const timeFormat = new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  function formatDuration(ms) {
    return ms >= 1000
      ? `${secondFormat.format(ms / 1000)} s (${msFormat.format(ms)} ms)`
      : `${msFormat.format(ms)} ms`;
  }

  function formatClock(ms) {
    return `${timeFormat.format(ms)}.${String(Math.floor(ms % 1000)).padStart(3, "0")}`;
  }

  function antivirusLine(event) {
    if (event.antivirus == null) {
      return "";
    }
    const span = event.end - event.start;
    const percent =
      span > 0 ? Math.min(Math.round((event.antivirus / span) * 100), 100) : 0;
    const share = span > 0 ? ` (${percent}%)` : "";
    return `${escapeHtml(antivirus)}: ${formatDuration(event.antivirus)}${share}`;
  }

  function tooltipHtml(event) {
    return [
      `<strong>${escapeHtml(event.name)}</strong>`,
      event.end - event.start
        ? `${escapeHtml(duration)}: ${formatDuration(event.end - event.start)}`
        : "",
      `${formatClock(event.start)} → ${formatClock(event.end)}`,
      event.score == null ? "" : `${escapeHtml(score)}: ${event.score}`,
      antivirusLine(event),
      ...[event.ips, event.tls].filter(Boolean).map(escapeHtml),
      event.transcript ? `<small>${escapeHtml(hint)}</small>` : "",
    ]
      .filter(Boolean)
      .join("<br/>");
  }

  const muted = toRgba("var(--color-muted-foreground)");
  const border = toRgba("var(--color-border)");
  const start = Math.min(...events.map((event) => event.start));
  const end = Math.max(...events.map((event) => event.end));
  const fontFamily = getComputedStyle(document.documentElement).fontFamily;

  function renderItem(params, api) {
    const categoryIndex = api.value(0);
    const from = api.coord([api.value(1), categoryIndex]);
    const to = api.coord([api.value(2), categoryIndex]);
    const height = api.size([0, 1])[1] * 0.6;
    const rectShape = echarts.graphic.clipRectByRect(
      {
        x: from[0],
        y: from[1] - height / 2,
        width: Math.max(to[0] - from[0], 3),
        height,
      },
      {
        x: params.coordSys.x,
        y: params.coordSys.y,
        width: params.coordSys.width,
        height: params.coordSys.height,
      },
    );
    if (!rectShape) {
      return null;
    }
    const name = events[categoryIndex]?.name ?? "";
    const inside = rectShape.width > 80;
    const characters = Math.floor((rectShape.width - 12) / 6.5);
    const label =
      inside && name.length > characters
        ? `${name.slice(0, Math.max(characters - 1, 0))}…`
        : name;
    const event = events[categoryIndex] ?? {};
    const span = event.end - event.start;
    const antivirusShare = span > 0 ? Math.min((event.antivirus ?? 0) / span, 1) : 0;
    // The scanner reports how long the scan ran, not when it started, so
    // the segment is a share of the bar rather than a place inside it.
    const inset = Math.min(3, rectShape.height / 4);
    const antivirusSegments =
      antivirusShare > 0
        ? [
            {
              type: "rect",
              transition: ["shape"],
              shape: {
                x: rectShape.x + inset,
                y: rectShape.y + inset,
                width: Math.max((rectShape.width - inset * 2) * antivirusShare, 2),
                height: rectShape.height - inset * 2,
              },
              style: {
                ...api.style(),
                fill: toRgba("var(--color-foreground)", 0.5),
              },
            },
          ]
        : [];
    return {
      type: "group",
      children: [
        {
          type: "rect",
          transition: ["shape"],
          shape: rectShape,
          style: api.style(),
        },
        ...antivirusSegments,
        {
          type: "text",
          style: {
            text: label,
            x: inside ? rectShape.x + 6 : rectShape.x + rectShape.width + 6,
            y: rectShape.y + rectShape.height / 2,
            fill: inside ? "#fff" : muted,
            verticalAlign: "middle",
            font: `12px ${fontFamily}`,
          },
        },
      ],
    };
  }

  element.style.height = `${events.length * 48 + 72}px`;
  const chart = echarts.init(element);
  chart.setOption({
    grid: { left: 8, right: 16, top: 8, bottom: 48, containLabel: true },
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (params) => tooltipHtml(params.data.event),
    },
    dataZoom: [
      {
        type: "slider",
        filterMode: "weakFilter",
        showDataShadow: false,
        bottom: 8,
        labelFormatter: "",
      },
      { type: "inside", filterMode: "weakFilter" },
    ],
    xAxis: {
      type: "value",
      min: start,
      max: end,
      scale: true,
      axisLabel: {
        color: muted,
        formatter: (value) =>
          end - start < 2000 ? formatClock(value) : timeFormat.format(value),
      },
      splitLine: { lineStyle: { color: border } },
    },
    yAxis: {
      type: "category",
      data: events.map((_, index) => index),
      inverse: true,
      show: false,
    },
    series: [
      {
        type: "custom",
        renderItem,
        itemStyle: { opacity: 0.8 },
        encode: { x: [1, 2], y: 0 },
        data: events.map((event, index) => ({
          name: event.name,
          value: [index, event.start, event.end],
          itemStyle: { color: toRgba(event.color) },
          event,
        })),
      },
    ],
  });
  chart.on("click", (params) => {
    const transcript = params.data?.event?.transcript;
    if (transcript) document.getElementById(transcript)?.showModal();
  });
  globalThis.addEventListener("resize", () => chart.resize());
}

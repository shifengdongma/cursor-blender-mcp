/**
 * Small dependency-free SVG chart builders for the compute platform.
 * Values are data-driven; no random series or timers are created here.
 */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.ComputeCharts = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  var PALETTE = ['#78bfd2', '#94ddf1', '#5fa8b8', '#d7a84f', '#c9876e', '#74c798'];

  function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text).replace(/[&<>"']/g, function(ch) {
      return {
        '&': '&amp;', '<': '&lt;', '>': '&gt;',
        '"': '&quot;', "'": '&#039;'
      }[ch];
    });
  }

  function emptyChart(message) {
    return '<div class="cp-chart-empty">' + escapeHtml(message || '暂无采集数据') + '</div>';
  }

  function numericValues(values) {
    return (values || []).filter(function(value) {
      return value !== null && value !== undefined && isFinite(Number(value));
    }).map(Number);
  }

  function formatNumber(value) {
    var number = Number(value);
    if (!isFinite(number)) return '—';
    if (Math.abs(number) >= 100) return String(Math.round(number));
    return String(Number(number.toFixed(1)));
  }

  function truncateLabel(label, length) {
    var text = String(label === null || label === undefined ? '' : label);
    if (text.length <= length) return text;
    return text.slice(0, Math.max(1, length - 1)) + '…';
  }

  function axisTicks(maxValue, count) {
    var max = Math.max(1, Number(maxValue) || 1);
    var ticks = [];
    for (var i = 0; i <= count; i += 1) {
      ticks.push((max / count) * i);
    }
    return ticks;
  }

  function barChart(options) {
    options = options || {};
    var labels = options.labels || [];
    var values = options.values || [];
    var numeric = numericValues(values);
    if (!labels.length || !numeric.length) {
      return emptyChart(options.emptyMessage || '暂无采集数据');
    }
    var width = 320, height = 180;
    var padL = 44, padR = 14, padT = 18, padB = 36;
    var innerW = width - padL - padR;
    var innerH = height - padT - padB;
    var maxValue = numeric.reduce(function(max, value) {
      return Math.max(max, value);
    }, 0);
    var yMax = Math.max(1, Number(options.yMax) || 0, maxValue);
    var ticks = axisTicks(yMax, 4);
    var barGap = Math.max(4, Math.min(12, innerW / Math.max(1, labels.length) * 0.18));
    var barWidth = Math.max(8, (innerW - (labels.length - 1) * barGap) / labels.length);
    var colors = options.colors || PALETTE;
    var unit = options.unit || '';
    var xAxisLabel = options.xAxisLabel || '';

    var svg = '<svg class="cp-svg-chart" viewBox="0 0 ' + width + ' ' + height +
      '" role="img" aria-label="' + escapeHtml(options.ariaLabel || options.title || '') + '">';
    for (var t = 0; t < ticks.length; t += 1) {
      var tickY = padT + innerH - (ticks[t] / yMax) * innerH;
      svg += '<line x1="' + padL + '" y1="' + tickY.toFixed(1) + '" x2="' +
        (width - padR) + '" y2="' + tickY.toFixed(1) +
        '" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>';
      svg += '<text x="' + (padL - 6) + '" y="' + (tickY + 3).toFixed(1) +
        '" text-anchor="end" fill="rgba(255,255,255,0.45)" font-size="9">' +
        escapeHtml(formatNumber(ticks[t])) + '</text>';
    }
    svg += '<text x="' + padL + '" y="10" fill="rgba(255,255,255,0.55)" font-size="9">' +
      escapeHtml(unit) + '</text>';

    for (var i = 0; i < labels.length; i += 1) {
      var value = Number(values[i]);
      var hasValue = values[i] !== null && values[i] !== undefined && isFinite(value);
      var x = padL + i * (barWidth + barGap);
      var barHeight = hasValue ? Math.max(0, (value / yMax) * innerH) : 0;
      var y = padT + innerH - barHeight;
      if (hasValue) {
        svg += '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) +
          '" width="' + barWidth.toFixed(1) + '" height="' + barHeight.toFixed(1) +
          '" rx="3" fill="' + escapeHtml(colors[i % colors.length]) + '">' +
          '<title>' + escapeHtml(String(labels[i])) + ': ' +
          escapeHtml(formatNumber(value)) + ' ' + escapeHtml(unit) + '</title></rect>';
        svg += '<text x="' + (x + barWidth / 2).toFixed(1) + '" y="' +
          (y - 5).toFixed(1) + '" text-anchor="middle" fill="rgba(255,255,255,0.62)" font-size="8">' +
          escapeHtml(formatNumber(value)) + '</text>';
      }
      svg += '<text x="' + (x + barWidth / 2).toFixed(1) + '" y="' +
        (padT + innerH + 16) + '" text-anchor="middle" fill="rgba(255,255,255,0.45)" font-size="8">' +
        escapeHtml(truncateLabel(labels[i], 8)) + '</text>';
    }
    if (xAxisLabel) {
      svg += '<text x="' + (padL + innerW / 2) + '" y="' + (height - 3) +
        '" text-anchor="middle" fill="rgba(255,255,255,0.4)" font-size="9">' +
        escapeHtml(xAxisLabel) + '</text>';
    }
    svg += '</svg>';
    return svg;
  }

  function lineChart(options) {
    options = options || {};
    var labels = options.labels || [];
    var values = options.values || [];
    var numeric = numericValues(values);
    if (!labels.length || numeric.length < 2) {
      return emptyChart(options.emptyMessage || '暂无采集数据');
    }
    var width = 320, height = 180;
    var padL = 44, padR = 14, padT = 18, padB = 36;
    var innerW = width - padL - padR;
    var innerH = height - padT - padB;
    var maxValue = numeric.reduce(function(max, value) {
      return Math.max(max, value);
    }, 0);
    var minValue = options.zeroBaseline ? 0 : numeric.reduce(function(min, value) {
      return Math.min(min, value);
    }, numeric[0]);
    var yMax = Number(options.yMax) || Math.max(1, maxValue);
    if (yMax <= minValue) yMax = minValue + 1;
    var ticks = axisTicks(yMax - minValue, 4).map(function(tick) {
      return tick + minValue;
    });
    var unit = options.unit || '';
    var color = options.color || '#78bfd2';
    var svg = '<svg class="cp-svg-chart" viewBox="0 0 ' + width + ' ' + height +
      '" role="img" aria-label="' + escapeHtml(options.ariaLabel || options.title || '') + '">';

    for (var t = 0; t < ticks.length; t += 1) {
      var tickY = padT + innerH - ((ticks[t] - minValue) / (yMax - minValue)) * innerH;
      svg += '<line x1="' + padL + '" y1="' + tickY.toFixed(1) + '" x2="' +
        (width - padR) + '" y2="' + tickY.toFixed(1) +
        '" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>';
      svg += '<text x="' + (padL - 6) + '" y="' + (tickY + 3).toFixed(1) +
        '" text-anchor="end" fill="rgba(255,255,255,0.45)" font-size="9">' +
        escapeHtml(formatNumber(ticks[t])) + '</text>';
    }
    svg += '<text x="' + padL + '" y="10" fill="rgba(255,255,255,0.55)" font-size="9">' +
      escapeHtml(unit) + '</text>';

    var points = [];
    var circles = '';
    for (var i = 0; i < labels.length; i += 1) {
      var value = values[i];
      if (value === null || value === undefined || !isFinite(Number(value))) continue;
      var x = padL + (i / Math.max(1, labels.length - 1)) * innerW;
      var y = padT + innerH - ((Number(value) - minValue) / (yMax - minValue)) * innerH;
      points.push(x.toFixed(1) + ',' + y.toFixed(1));
      circles += '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) +
        '" r="2.8" fill="' + escapeHtml(color) + '">' +
        '<title>' + escapeHtml(String(labels[i])) + ': ' +
        escapeHtml(formatNumber(value)) + ' ' + escapeHtml(unit) + '</title></circle>';
    }
    if (points.length < 2) return emptyChart(options.emptyMessage || '暂无采集数据');
    var areaPoints = padL + ',' + (padT + innerH) + ' ' + points.join(' ') + ' ' +
      (padL + innerW) + ',' + (padT + innerH);
    svg += '<polygon points="' + areaPoints + '" fill="' + escapeHtml(color) +
      '" fill-opacity="0.09"/>';
    svg += '<polyline points="' + points.join(' ') + '" fill="none" stroke="' +
      escapeHtml(color) + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
    svg += circles;

    var labelStep = Math.max(1, Math.ceil(labels.length / 6));
    for (var l = 0; l < labels.length; l += labelStep) {
      var labelX = padL + (l / Math.max(1, labels.length - 1)) * innerW;
      svg += '<text x="' + labelX.toFixed(1) + '" y="' + (padT + innerH + 16) +
        '" text-anchor="middle" fill="rgba(255,255,255,0.45)" font-size="8">' +
        escapeHtml(truncateLabel(labels[l], 9)) + '</text>';
    }
    if (options.xAxisLabel) {
      svg += '<text x="' + (padL + innerW / 2) + '" y="' + (height - 3) +
        '" text-anchor="middle" fill="rgba(255,255,255,0.4)" font-size="9">' +
        escapeHtml(options.xAxisLabel) + '</text>';
    }
    svg += '</svg>';
    return svg;
  }

  function donutChart(options) {
    options = options || {};
    var items = (options.items || []).filter(function(item) {
      return item && Number(item.value) > 0;
    });
    if (!items.length) return emptyChart(options.emptyMessage || '暂无采集数据');
    var total = items.reduce(function(sum, item) {
      return sum + Number(item.value);
    }, 0);
    var width = 320, height = 180;
    var cx = 112, cy = 84, outer = 54, inner = 34;
    var colors = options.colors || PALETTE;
    var unit = options.unit || '';
    var svg = '<svg class="cp-svg-chart" viewBox="0 0 ' + width + ' ' + height +
      '" role="img" aria-label="' + escapeHtml(options.ariaLabel || options.title || '') + '">';
    var cumulative = 0;
    for (var i = 0; i < items.length; i += 1) {
      var value = Number(items[i].value);
      var startAngle = (cumulative / total) * Math.PI * 2 - Math.PI / 2;
      var endAngle = ((cumulative + value) / total) * Math.PI * 2 - Math.PI / 2;
      cumulative += value;
      var largeArc = endAngle - startAngle > Math.PI ? 1 : 0;
      var x1 = cx + outer * Math.cos(startAngle);
      var y1 = cy + outer * Math.sin(startAngle);
      var x2 = cx + outer * Math.cos(endAngle);
      var y2 = cy + outer * Math.sin(endAngle);
      var x3 = cx + inner * Math.cos(endAngle);
      var y3 = cy + inner * Math.sin(endAngle);
      var x4 = cx + inner * Math.cos(startAngle);
      var y4 = cy + inner * Math.sin(startAngle);
      var path = 'M' + x1.toFixed(1) + ',' + y1.toFixed(1) +
        ' A' + outer + ',' + outer + ' 0 ' + largeArc + ' 1 ' + x2.toFixed(1) + ',' + y2.toFixed(1) +
        ' L' + x3.toFixed(1) + ',' + y3.toFixed(1) +
        ' A' + inner + ',' + inner + ' 0 ' + largeArc + ' 0 ' + x4.toFixed(1) + ',' + y4.toFixed(1) + ' Z';
      svg += '<path d="' + path + '" fill="' +
        escapeHtml(items[i].color || colors[i % colors.length]) + '">' +
        '<title>' + escapeHtml(items[i].label) + ': ' + value + ' ' + escapeHtml(unit) +
        '</title></path>';
    }
    svg += '<text x="' + cx + '" y="' + (cy - 3) + '" text-anchor="middle" fill="rgba(255,255,255,0.85)" font-size="16" font-weight="600">' +
      escapeHtml(formatNumber(total)) + '</text>';
    svg += '<text x="' + cx + '" y="' + (cy + 13) + '" text-anchor="middle" fill="rgba(255,255,255,0.45)" font-size="8">' +
      escapeHtml(unit) + '</text>';
    var legendX = 200;
    for (var l = 0; l < items.length; l += 1) {
      var y = 38 + l * 20;
      svg += '<rect x="' + legendX + '" y="' + (y - 8) + '" width="8" height="8" rx="2" fill="' +
        escapeHtml(items[l].color || colors[l % colors.length]) + '"/>';
      svg += '<text x="' + (legendX + 14) + '" y="' + y + '" fill="rgba(255,255,255,0.6)" font-size="9">' +
        escapeHtml(truncateLabel(items[l].label, 12)) + ' · ' +
        escapeHtml(formatNumber(items[l].value)) + '</text>';
    }
    svg += '</svg>';
    return svg;
  }

  return {
    PALETTE: PALETTE,
    escapeHtml: escapeHtml,
    emptyChart: emptyChart,
    barChart: barChart,
    lineChart: lineChart,
    donutChart: donutChart
  };
});

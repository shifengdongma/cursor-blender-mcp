'use strict';

var assert = require('assert');
var fs = require('fs');
var path = require('path');
var charts = require('../../web/compute-charts.js');

var ROOT = path.resolve(__dirname, '..', '..');

function testBarChartHasAxesAndUnits() {
  var svg = charts.barChart({
    labels: ['本地', '私有', '云', '边缘'],
    values: [38, 62, 45, 18],
    unit: '%',
    xAxisLabel: '资源池',
    title: 'GPU 利用率'
  });
  assert.ok(svg.indexOf('<svg') !== -1);
  assert.ok(svg.indexOf('GPU 利用率') !== -1);
  assert.ok(svg.indexOf('资源池') !== -1);
  assert.ok(svg.indexOf('>%<') !== -1);
  assert.ok(svg.indexOf('<title>') !== -1);
  assert.ok(svg.indexOf('38') !== -1);
}

function testLineChartHandlesGapsAndEmptyData() {
  var svg = charts.lineChart({
    labels: ['S1', 'S2', 'S3', 'S4'],
    values: [3, null, 5, 6],
    unit: '个',
    zeroBaseline: true,
    title: '任务趋势'
  });
  assert.ok(svg.indexOf('<polyline') !== -1);
  assert.ok(svg.indexOf('任务趋势') !== -1);
  var empty = charts.lineChart({
    labels: ['S1', 'S2'], values: [null, null], unit: '个'
  });
  assert.ok(empty.indexOf('cp-chart-empty') !== -1);
}

function testDonutChartAndEmptyState() {
  var svg = charts.donutChart({
    items: [
      { label: '本地', value: 1 },
      { label: '私有', value: 1 },
      { label: '云', value: 1 },
      { label: '边缘', value: 1 }
    ],
    unit: '台',
    title: '资源池分布'
  });
  assert.ok(svg.indexOf('<path') !== -1);
  assert.ok(svg.indexOf('资源池分布') !== -1);
  assert.ok(svg.indexOf('台') !== -1);
  assert.ok(charts.donutChart({ items: [] }).indexOf('cp-chart-empty') !== -1);
}

function testLabelsAreEscaped() {
  var svg = charts.barChart({
    labels: ['<script>alert(1)</script>'],
    values: [1],
    unit: '个'
  });
  assert.ok(svg.indexOf('<script>') === -1);
  assert.ok(svg.indexOf('&lt;script&gt;') !== -1);
}

function testSourceHasNoRandomness() {
  var source = fs.readFileSync(
    path.join(ROOT, 'web/compute-charts.js'), 'utf8'
  );
  assert.ok(source.indexOf('Math.random') === -1);
  assert.ok(source.indexOf('setInterval') === -1);
}

testBarChartHasAxesAndUnits();
testLineChartHandlesGapsAndEmptyData();
testDonutChartAndEmptyState();
testLabelsAreEscaped();
testSourceHasNoRandomness();
console.log('compute chart tests passed');

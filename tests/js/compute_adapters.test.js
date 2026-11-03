'use strict';

var assert = require('assert');
var fs = require('fs');
var path = require('path');
var adapters = require('../../web/compute-adapters.js');

var ROOT = path.resolve(__dirname, '..', '..');

function testMonitoringNodeVramMapping() {
  var nodes = adapters.adaptMonitoringNodes([{
    id: 'node-1',
    node_name: '主机 01',
    provider_type: 'cloud',
    gpu_type: 'A100 80GB',
    gpu_count: 4,
    gpu_memory_mb: 81920,
    latest_gpu_percent: 62,
    latest_memory_percent: 91,
    latest_gpu_memory_percent: 50,
    latest_gpu_temperature: 68,
    status: 'online'
  }]);
  assert.strictEqual(nodes.length, 1);
  assert.strictEqual(nodes[0].vramPerGpuGb, 80);
  assert.strictEqual(nodes[0].totalVramGb, 320);
  assert.strictEqual(nodes[0].usedVramGb, 160);
  assert.strictEqual(nodes[0].utilizationPct, 62);
  assert.strictEqual(nodes[0].temperatureC, 68);
  assert.strictEqual(nodes[0].unitPricePerHour, null);
  assert.strictEqual(nodes[0].source, 'live');
}

function testMissingValuesStayNull() {
  var nodes = adapters.adaptMonitoringNodes([{
    id: 'node-2', node_name: '主机 02', gpu_count: 2, status: 'unknown'
  }]);
  assert.strictEqual(nodes[0].vramPerGpuGb, null);
  assert.strictEqual(nodes[0].totalVramGb, null);
  assert.strictEqual(nodes[0].usedVramGb, null);
  assert.strictEqual(nodes[0].utilizationPct, null);

  var links = adapters.adaptMonitoringLinks([{
    id: 'link-1', target: '10.0.0.2:9100', success: true, latency_ms: null
  }]);
  assert.strictEqual(links[0].latencyMs, null);
  assert.strictEqual(links[0].bandwidthGbps, null);
  assert.strictEqual(links[0].throughputGbps, null);
}

function testLinkFailureAndStorage() {
  var links = adapters.adaptMonitoringLinks([{
    id: 'link-down', target: '10.0.0.3:9100', success: false,
    latency_ms: 120, packet_loss_pct: 2.5
  }]);
  assert.strictEqual(links[0].status, 'down');
  assert.strictEqual(links[0].health, 'warning');
  assert.strictEqual(links[0].packetLossPct, 2.5);

  var storage = adapters.adaptStorage([{
    label: '素材库', path: '/data/assets', total_bytes: 2000000000000,
    used_bytes: 1940000000000, usage_pct: 97
  }], {});
  assert.strictEqual(storage[0].capacityTB, 2);
  assert.strictEqual(storage[0].usedTB, 1.94);
  assert.strictEqual(storage[0].readMBps, null);
  assert.strictEqual(storage[0].connections, null);
  assert.strictEqual(storage[0].status, 'warning');
}

function testAlertStatuses() {
  assert.strictEqual(adapters.isActiveAlert('open'), true);
  assert.strictEqual(adapters.isActiveAlert('acknowledged'), true);
  assert.strictEqual(adapters.isActiveAlert('processing'), true);
  assert.strictEqual(adapters.isActiveAlert('recovered'), false);
  assert.strictEqual(adapters.isActiveAlert('closed'), false);

  var alerts = adapters.adaptAlerts([{
    id: 'alert-1', severity: 'critical', target_type: 'node',
    target_id: 'node-1', metric_name: 'gpu_percent', current_value: 98,
    threshold_value: 90, status: 'open', created_at: 1700000000
  }]);
  assert.strictEqual(alerts[0].level, 'critical');
  assert.strictEqual(alerts[0].type, 'node');
  assert.strictEqual(alerts[0].status, 'open');
  assert.strictEqual(adapters.isActiveAlert(alerts[0].status), true);
  assert.ok(alerts[0].reason.indexOf('gpu_percent') !== -1);
}

function testLiveSceneDoesNotFabricateShowcaseValues() {
  var scene = adapters.sceneFromLive({
    nodes: [{
      id: 'node-1', node_name: '主机 01', gpu_count: 2,
      gpu_memory_mb: 24576, latest_gpu_percent: 40, status: 'online'
    }],
    links: [],
    samples: [],
    storage: { targets: [], summary: {} },
    alerts: [],
    renderJobs: []
  });
  assert.strictEqual(scene.source, 'live');
  assert.strictEqual(scene.nodes.length, 1);
  assert.strictEqual(scene.networkLinks.length, 0);
  assert.strictEqual(scene.storageNodes.length, 0);
  assert.strictEqual(scene.overview.avgGpuUtilPct, null);
  assert.strictEqual(scene.overview.avgNetworkLatencyMs, null);
}

function testSourceHasNoRandomness() {
  var source = fs.readFileSync(
    path.join(ROOT, 'web/compute-adapters.js'), 'utf8'
  );
  assert.ok(source.indexOf('Math.random') === -1);
}

testMonitoringNodeVramMapping();
testMissingValuesStayNull();
testLinkFailureAndStorage();
testAlertStatuses();
testLiveSceneDoesNotFabricateShowcaseValues();
testSourceHasNoRandomness();
console.log('compute adapter tests passed');

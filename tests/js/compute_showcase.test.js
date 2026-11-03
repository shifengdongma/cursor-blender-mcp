'use strict';

var assert = require('assert');
var fs = require('fs');
var path = require('path');
var showcase = require('../../web/compute-showcase-data.js');

var ROOT = path.resolve(__dirname, '..', '..');
var scene = showcase.buildScene();

function testSceneIsValidAndStable() {
  assert.deepStrictEqual(showcase.validateScene(scene), []);
  assert.deepStrictEqual(
    JSON.parse(JSON.stringify(scene)),
    JSON.parse(JSON.stringify(showcase.buildScene()))
  );
  assert.strictEqual(scene.source, 'showcase');
  assert.strictEqual(scene.nodes.length, 4);
  assert.strictEqual(scene.overview.totalNodes, 4);
  assert.strictEqual(scene.overview.onlineNodes, 4);
  assert.strictEqual(scene.overview.queuedTasks, 2);
  assert.strictEqual(scene.overview.runningTasks, 4);
  assert.strictEqual(scene.pools.length, 4);
  assert.strictEqual(
    scene.pools.reduce(function(total, pool) { return total + pool.nodeCount; }, 0),
    4
  );
  assert.strictEqual(
    scene.pools.reduce(function(total, pool) { return total + pool.gpuCount; }, 0),
    12
  );
}

function testDerivedMetricsAreConsistent() {
  var totalGpus = scene.nodes.reduce(function(total, node) {
    return total + node.gpuCount;
  }, 0);
  var weighted = scene.nodes.reduce(function(total, node) {
    return total + node.utilizationPct * node.gpuCount;
  }, 0) / totalGpus;
  assert.strictEqual(scene.overview.avgGpuUtilPct, Number(weighted.toFixed(1)));
  assert.strictEqual(
    scene.gpuTrend.values[scene.gpuTrend.values.length - 1],
    scene.overview.avgGpuUtilPct
  );
  assert.strictEqual(
    scene.taskTrend.values[scene.taskTrend.values.length - 1],
    scene.overview.queuedTasks + scene.overview.runningTasks
  );
  var expectedLatency = scene.networkLinks.reduce(function(total, link) {
    return total + link.latencyMs;
  }, 0) / scene.networkLinks.length;
  assert.strictEqual(
    scene.overview.avgNetworkLatencyMs,
    Number(expectedLatency.toFixed(1))
  );
  assert.strictEqual(
    scene.nodes.reduce(function(total, node) { return total + node.queuedTasks; }, 0),
    scene.overview.queuedTasks
  );
}

function testTopologyAndSessionReferences() {
  assert.strictEqual(showcase.validateScene(scene).length, 0);
  var nodeIds = {};
  scene.nodes.forEach(function(node) { nodeIds[node.id] = true; });
  scene.topology.links.forEach(function(link) {
    assert.ok(nodeIds[link.source], link.source);
    assert.ok(nodeIds[link.target], link.target);
    assert.ok(scene.networkLinks.some(function(networkLink) {
      return networkLink.id === link.id;
    }));
  });
  scene.sessions.forEach(function(session) {
    assert.ok(nodeIds[session.nodeId], session.nodeId);
    assert.ok(session.id && session.project && session.engine);
  });
}

function testImagesAreLocalAndExist() {
  var keys = Object.keys(scene.images);
  assert.ok(keys.length >= 8);
  keys.forEach(function(key) {
    var imagePath = scene.images[key];
    assert.ok(imagePath.indexOf('/web/assets/showcase/') === 0, imagePath);
    assert.ok(imagePath.indexOf('http') === -1, imagePath);
    var diskPath = path.join(ROOT, imagePath.replace(/^\//, ''));
    assert.ok(fs.existsSync(diskPath), diskPath);
  });
}

function testNoOfficialBillingDataInScene() {
  var serialized = JSON.stringify(scene);
  assert.ok(serialized.indexOf('volcengine') === -1);
  assert.ok(serialized.indexOf('officialBilling') === -1);
  assert.ok(scene.officialBilling === undefined);
  assert.ok(scene.volcengine === undefined);
}

function testSourceHasNoRandomness() {
  var source = fs.readFileSync(
    path.join(ROOT, 'web/compute-showcase-data.js'), 'utf8'
  );
  assert.ok(source.indexOf('Math.random') === -1);
  assert.ok(source.indexOf('Date.now') === -1);
  assert.ok(source.indexOf('setInterval') === -1);
}

testSceneIsValidAndStable();
testDerivedMetricsAreConsistent();
testTopologyAndSessionReferences();
testImagesAreLocalAndExist();
testNoOfficialBillingDataInScene();
testSourceHasNoRandomness();
console.log('compute showcase tests passed');

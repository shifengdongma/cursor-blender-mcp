'use strict';

var assert = require('assert');
var fs = require('fs');
var path = require('path');
var scheduling = require('../../web/compute-scheduling.js');

var ROOT = path.resolve(__dirname, '..', '..');

function node(overrides) {
  return Object.assign({
    id: 'node-a',
    name: '节点 A',
    pool: 'local-workspace',
    gpuModel: 'RTX 4090',
    gpuCount: 2,
    vramPerGpuGb: 24,
    utilizationPct: 30,
    status: 'online',
    schedulable: true,
    queuedTasks: 0,
    latencyMs: 10,
    unitPricePerHour: 5
  }, overrides || {});
}

function request(overrides) {
  return Object.assign({
    taskName: '测试任务',
    taskType: 'render',
    priority: 'medium',
    gpuCount: 1,
    minVram: 16,
    maxCost: 0,
    maxLatency: 0,
    strategy: 'lowest_cost'
  }, overrides || {});
}

function testHardConstraints() {
  var offline = scheduling.evaluateCandidates(
    [node({ id: 'offline', status: 'offline' })],
    request()
  );
  assert.strictEqual(offline.candidates.length, 0);
  assert.ok(offline.rejected[0].reasons.indexOf('节点不在线或不可调度') !== -1);

  var insufficientGpu = scheduling.evaluateCandidates(
    [node({ gpuCount: 1 })],
    request({ gpuCount: 2 })
  );
  assert.strictEqual(insufficientGpu.candidates.length, 0);

  var insufficientVram = scheduling.evaluateCandidates(
    [node({ vramPerGpuGb: 16 })],
    request({ minVram: 24 })
  );
  assert.strictEqual(insufficientVram.candidates.length, 0);

  var overBudget = scheduling.evaluateCandidates(
    [node({ unitPricePerHour: 20 })],
    request({ gpuCount: 2, maxCost: 30 })
  );
  assert.strictEqual(overBudget.candidates.length, 0);
  assert.ok(overBudget.rejected[0].reasons.indexOf('超过预算上限') !== -1);

  var unknownPrice = scheduling.evaluateCandidates(
    [node({ unitPricePerHour: null })],
    request({ maxCost: 30 })
  );
  assert.strictEqual(unknownPrice.candidates.length, 0);
  assert.ok(unknownPrice.rejected[0].reasons.some(function(reason) {
    return reason.indexOf('缺少参考单价') !== -1;
  }));

  var unknownLatency = scheduling.evaluateCandidates(
    [node({ latencyMs: null })],
    request({ maxLatency: 20 })
  );
  assert.strictEqual(unknownLatency.candidates.length, 0);
  assert.ok(unknownLatency.rejected[0].reasons.some(function(reason) {
    return reason.indexOf('缺少网络时延') !== -1;
  }));

  var passed = scheduling.evaluateCandidates(
    [node({})],
    request({ maxCost: 20, maxLatency: 20 })
  );
  assert.strictEqual(passed.candidates.length, 1);
}

function testNoCandidatesReturnsEmptyResult() {
  var result = scheduling.evaluate(
    [node({ status: 'offline' })],
    request()
  );
  assert.strictEqual(result.recommendations.length, 0);
  assert.strictEqual(result.ranked.length, 0);
  assert.strictEqual(result.rejectedCount, 1);
}

function testStrategiesChangeRanking() {
  var cheap = node({
    id: 'cheap', name: '低价节点', pool: 'local-workspace',
    unitPricePerHour: 5, latencyMs: 60, queuedTasks: 2,
    utilizationPct: 30, vramPerGpuGb: 24
  });
  var fast = node({
    id: 'fast', name: '低时延节点', pool: 'cloud-gpu',
    unitPricePerHour: 20, latencyMs: 5, queuedTasks: 0,
    utilizationPct: 40, vramPerGpuGb: 80
  });
  var lowCost = scheduling.evaluate([cheap, fast], request({ strategy: 'lowest_cost' }));
  var lowLatency = scheduling.evaluate([cheap, fast], request({ strategy: 'lowest_latency' }));
  var shortQueue = scheduling.evaluate([cheap, fast], request({ strategy: 'shortest_queue' }));
  var localFirst = scheduling.evaluate([cheap, fast], request({ strategy: 'local_first' }));
  assert.strictEqual(lowCost.recommendations[0].nodeId, 'cheap');
  assert.strictEqual(lowLatency.recommendations[0].nodeId, 'fast');
  assert.strictEqual(shortQueue.recommendations[0].nodeId, 'fast');
  assert.strictEqual(localFirst.recommendations[0].nodeId, 'cheap');

  var first = scheduling.evaluate([cheap, fast], request());
  var second = scheduling.evaluate([cheap, fast], request());
  assert.deepStrictEqual(first, second);
}

function testStateMachine() {
  assert.strictEqual(scheduling.canTransition('pending', 'recommended'), true);
  assert.strictEqual(scheduling.canTransition('pending', 'running'), false);
  assert.strictEqual(scheduling.nextState('pending'), 'recommended');
  assert.strictEqual(scheduling.nextState('recommended'), 'queued');
  assert.strictEqual(scheduling.nextState('queued'), 'running');
  assert.strictEqual(scheduling.nextState('running'), 'completed');
  assert.strictEqual(scheduling.nextState('completed'), 'completed');
  assert.strictEqual(scheduling.transition('pending', 'running'), 'pending');
}

function testSourceHasNoRandomness() {
  var source = fs.readFileSync(
    path.join(ROOT, 'web/compute-scheduling.js'), 'utf8'
  );
  assert.ok(source.indexOf('Math.random') === -1);
  assert.ok(source.indexOf('setInterval') === -1);
}

testHardConstraints();
testNoCandidatesReturnsEmptyResult();
testStrategiesChangeRanking();
testStateMachine();
testSourceHasNoRandomness();
console.log('compute scheduling tests passed');

'use strict';

var assert = require('assert');
var core = require('../../web/content-audit-core.js');

function testNormalizeKeywords() {
  var normalized = core.normalizeKeywords([
    ' 未授权素材 ',
    { text: '涉密资料', enabled: false },
    '未授权素材',
    '',
    '个人身份信息'
  ]);
  assert.strictEqual(normalized.length, 3);
  assert.strictEqual(normalized[0].text, '未授权素材');
  assert.strictEqual(normalized[0].enabled, true);
  assert.strictEqual(normalized[1].text, '涉密资料');
  assert.strictEqual(normalized[1].enabled, false);
  assert.strictEqual(normalized[2].text, '个人身份信息');

  var many = [];
  for (var i = 0; i < 30; i += 1) many.push('keyword-' + i);
  assert.strictEqual(core.normalizeKeywords(many).length, core.MAX_KEYWORDS);
}

function testBasicScanAndMask() {
  var result = core.scanText(
    '这是未授权素材，包含涉密资料。',
    ['未授权素材', '涉密资料'],
    { mode: 'mask' }
  );
  assert.strictEqual(result.status, 'flagged');
  assert.strictEqual(result.hitCount, 2);
  assert.deepStrictEqual(
    result.matchedKeywords.sort(),
    ['未授权素材', '涉密资料'].sort()
  );
  assert.strictEqual(result.maskedText.length, result.text.length);
  assert.ok(result.maskedText.indexOf('未授权素材') === -1);
  assert.ok(result.maskedText.indexOf('涉密资料') === -1);
  assert.ok(result.maskedText.indexOf('这是') === 0);
  assert.strictEqual(result.segments.map(function(segment) {
    return segment.text;
  }).join(''), result.text);
}

function testCaseInsensitiveAndDisabledRules() {
  var result = core.scanText(
    'Secret and secret',
    [
      { text: 'secret', enabled: true },
      { text: 'and', enabled: false }
    ],
    { mode: 'mark' }
  );
  assert.strictEqual(result.hitCount, 2);
  assert.deepStrictEqual(result.matchedKeywords, ['secret']);
  assert.strictEqual(result.maskedText, '****** and ******');
  assert.strictEqual(result.maskedText.indexOf('and'), 7);
}

function testOverlappingKeywords() {
  var result = core.scanText(
    '个人身份信息需要保护',
    ['个人身份信息', '身份'],
    { mode: 'mask' }
  );
  assert.strictEqual(result.hitCount, 2);
  assert.strictEqual(result.matchedKeywords.length, 2);
  assert.strictEqual(result.ranges.length, 1);
  assert.strictEqual(result.ranges[0].start, 0);
  assert.strictEqual(result.ranges[0].end, 6);
  assert.strictEqual(
    result.maskedText.slice(0, 6),
    '******'
  );
}

function testHtmlPayloadStaysText() {
  var payload = '<img src=x onerror=alert(1)>';
  var result = core.scanText(payload, ['img'], { mode: 'mark' });
  assert.strictEqual(result.status, 'flagged');
  assert.strictEqual(result.segments.map(function(segment) {
    return segment.text;
  }).join(''), payload);
  assert.strictEqual(result.maskedText.slice(0, 4), '<***');
  assert.ok(result.maskedText.indexOf('<img') === -1);
}

function testEmptyInput() {
  var result = core.scanText('', ['涉密资料'], { mode: 'mask' });
  assert.strictEqual(result.status, 'passed');
  assert.strictEqual(result.hitCount, 0);
  assert.deepStrictEqual(result.matchedKeywords, []);
  assert.strictEqual(result.maskedText, '');
  assert.deepStrictEqual(result.segments, []);
}

function testNewlinesPreserved() {
  var result = core.scanText('第一行\n涉密资料\n第三行', ['涉密资料'], {
    mode: 'mask'
  });
  assert.ok(result.maskedText.indexOf('\n') !== -1);
  assert.strictEqual(result.maskedText.split('\n').length, 3);
  assert.strictEqual(result.maskedText.split('\n')[1], '****');
}

testNormalizeKeywords();
testBasicScanAndMask();
testCaseInsensitiveAndDisabledRules();
testOverlappingKeywords();
testHtmlPayloadStaysText();
testEmptyInput();
testNewlinesPreserved();
console.log('content audit tests passed');

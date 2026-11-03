/**
 * Pure keyword-scanning helpers for the creative studio audit preview.
 * No DOM access and no user-supplied regular expressions.
 */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.ContentAuditCore = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  var MAX_KEYWORDS = 20;

  function normalizeText(value) {
    return value === null || value === undefined ? '' : String(value);
  }

  function normalizeKeywords(input) {
    var list = [];
    if (Array.isArray(input)) {
      list = input;
    } else if (typeof input === 'string') {
      list = input.split(',');
    }
    var seen = {};
    var result = [];
    for (var i = 0; i < list.length; i += 1) {
      var item = list[i];
      var text;
      var enabled = true;
      if (item && typeof item === 'object') {
        text = item.text !== undefined ? item.text : item.keyword;
        enabled = item.enabled !== false;
      } else {
        text = item;
      }
      text = normalizeText(text).trim();
      if (!text) continue;
      var key = text.toLowerCase();
      if (seen[key]) continue;
      seen[key] = true;
      result.push({ text: text, enabled: enabled });
      if (result.length >= MAX_KEYWORDS) break;
    }
    return result;
  }

  function mergeRanges(hits) {
    var sorted = hits.slice().sort(function(a, b) {
      return a.start - b.start || b.length - a.length;
    });
    var ranges = [];
    for (var i = 0; i < sorted.length; i += 1) {
      var hit = sorted[i];
      var start = hit.start;
      var end = hit.start + hit.length;
      var last = ranges[ranges.length - 1];
      if (last && start <= last.end) {
        if (end > last.end) last.end = end;
        if (last.keywords.indexOf(hit.keyword) === -1) {
          last.keywords.push(hit.keyword);
        }
      } else {
        ranges.push({ start: start, end: end, keywords: [hit.keyword] });
      }
    }
    return ranges;
  }

  function repeatStar(count) {
    var out = '';
    for (var i = 0; i < count; i += 1) out += '*';
    return out;
  }

  function scanText(text, keywords, options) {
    text = normalizeText(text);
    options = options || {};
    var enabled = normalizeKeywords(keywords).filter(function(item) {
      return item.enabled;
    });
    var lower = text.toLowerCase();
    var hits = [];
    var matched = {};
    for (var i = 0; i < enabled.length; i += 1) {
      var needle = enabled[i].text.toLowerCase();
      if (!needle) continue;
      var from = 0;
      while (from <= lower.length - needle.length) {
        var index = lower.indexOf(needle, from);
        if (index === -1) break;
        hits.push({
          keyword: enabled[i].text,
          start: index,
          length: needle.length
        });
        matched[enabled[i].text] = true;
        from = index + Math.max(1, needle.length);
      }
    }
    hits.sort(function(a, b) {
      return a.start - b.start || b.length - a.length;
    });

    var ranges = mergeRanges(hits);
    var segments = [];
    var cursor = 0;
    for (var r = 0; r < ranges.length; r += 1) {
      var range = ranges[r];
      if (range.start > cursor) {
        segments.push({ text: text.slice(cursor, range.start), hit: false });
      }
      segments.push({
        text: text.slice(range.start, range.end),
        hit: true,
        keywords: range.keywords.slice()
      });
      cursor = range.end;
    }
    if (cursor < text.length) {
      segments.push({ text: text.slice(cursor), hit: false });
    }

    var maskedText = '';
    cursor = 0;
    for (var m = 0; m < ranges.length; m += 1) {
      maskedText += text.slice(cursor, ranges[m].start);
      maskedText += repeatStar(ranges[m].end - ranges[m].start);
      cursor = ranges[m].end;
    }
    maskedText += text.slice(cursor);

    var matchedKeywords = Object.keys(matched);
    return {
      text: text,
      hits: hits,
      hitCount: hits.length,
      matchedKeywords: matchedKeywords,
      ranges: ranges,
      segments: segments,
      maskedText: maskedText,
      mode: options.mode === 'mark' ? 'mark' : 'mask',
      status: hits.length ? 'flagged' : 'passed'
    };
  }

  return {
    MAX_KEYWORDS: MAX_KEYWORDS,
    normalizeKeywords: normalizeKeywords,
    mergeRanges: mergeRanges,
    scanText: scanText
  };
});

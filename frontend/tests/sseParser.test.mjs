import assert from 'node:assert/strict'
import test from 'node:test'
import { parseSseBlock } from '../src/shared/api/sseParser.mjs'

test('reads event name, replay id, and JSON data', () => {
  assert.deepEqual(parseSseBlock('event: message.delta\nid: 12-0\ndata: {"content":"hi"}'), {
    event: 'message.delta',
    id: '12-0',
    data: { content: 'hi' },
  })
})

test('joins multiple data lines and ignores comments', () => {
  assert.deepEqual(parseSseBlock(': keepalive\ndata: {\ndata: "ok": true\ndata: }'), {
    event: null,
    id: null,
    data: { 'ok': true },
  })
})

test('ignores an id containing a null character', () => {
  assert.deepEqual(parseSseBlock('id: bad\0id\ndata: {}'), {
    event: null,
    id: null,
    data: {},
  })
})


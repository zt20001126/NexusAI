import assert from 'node:assert/strict'
import test from 'node:test'
import { parseSseBlock } from '../src/shared/api/sseParser.mjs'

test('reads the protocol event name, replay id, and four-field JSON event', () => {
  assert.deepEqual(parseSseBlock(
    'event: message\nid: 12-0\ndata: {"event_id":"12-0","event_type":"message","timestamp":"2026-10-20T02:50:00Z","data":{"operation":"delta","message_id":"m1","block_id":"b1","offset":0,"text":"hi"}}',
  ), {
    event: 'message',
    id: '12-0',
    data: {
      event_id: '12-0',
      event_type: 'message',
      timestamp: '2026-10-20T02:50:00Z',
      data: { operation: 'delta', message_id: 'm1', block_id: 'b1', offset: 0, text: 'hi' },
    },
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


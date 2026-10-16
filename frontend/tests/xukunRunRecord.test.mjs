import assert from 'node:assert/strict'
import test from 'node:test'

import {
  BEST_TIME_STORAGE_KEY,
  formatRunTime,
  readBestTime,
  saveBestTime,
} from '../src/features/dino-run/model/record.mjs'

function createStorage(initialValue = null) {
  const entries = new Map()
  if (initialValue !== null) entries.set(BEST_TIME_STORAGE_KEY, initialValue)
  return {
    entries,
    getItem(key) {
      return entries.get(key) ?? null
    },
    setItem(key, value) {
      entries.set(key, value)
    },
  }
}

test('reads a valid best time and treats invalid stored values as empty', () => {
  assert.equal(readBestTime(createStorage('12500')), 12500)
  assert.equal(readBestTime(createStorage('not-a-time')), 0)
  assert.equal(readBestTime(createStorage('-1')), 0)
  assert.equal(readBestTime(null), 0)
})

test('saves only a new personal best', () => {
  const storage = createStorage('9000')

  assert.equal(saveBestTime(storage, 8500), 9000)
  assert.equal(saveBestTime(storage, 12123.9), 12123)
  assert.equal(storage.getItem(BEST_TIME_STORAGE_KEY), '12123')
})

test('returns the prior record if browser storage is unavailable', () => {
  const storage = {
    getItem: () => null,
    setItem: () => { throw new Error('storage disabled') },
  }

  assert.equal(saveBestTime(storage, 3000), 0)
})

test('formats elapsed duration as minutes and seconds without a score', () => {
  assert.equal(formatRunTime(0), '00:00')
  assert.equal(formatRunTime(59999), '00:59')
  assert.equal(formatRunTime(60000), '01:00')
  assert.equal(formatRunTime(-1), '00:00')
})

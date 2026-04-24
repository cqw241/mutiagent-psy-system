import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldMountLocalCameraVideo } from './VideoCallPanel.helpers.js'

test('shouldMountLocalCameraVideo keeps the video element mounted before camera readiness', () => {
  assert.equal(
    shouldMountLocalCameraVideo({
      isActive: false,
      isCameraReady: false,
    }),
    true,
  )
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { uploadFile } from './upload'

class FakeXhr {
  static last: FakeXhr
  status = 0
  response: unknown = null
  responseType = ''
  upload: { onprogress?: (e: ProgressEvent) => void } = {}
  onload?: () => void
  onerror?: () => void
  open = vi.fn()
  send = vi.fn()
  constructor() {
    FakeXhr.last = this
  }
}

const file = new File(['x'], 'talk.mp3', { type: 'audio/mpeg' })

function upload() {
  return uploadFile(file, () => {})
}

function answer(status: number, body: unknown) {
  FakeXhr.last.status = status
  FakeXhr.last.response = body
  FakeXhr.last.onload?.()
}

describe('uploadFile', () => {
  beforeEach(() => vi.stubGlobal('XMLHttpRequest', FakeXhr))
  afterEach(() => vi.unstubAllGlobals())

  it('resolves with the job the server created', async () => {
    const pending = upload()
    answer(201, { id: 'a1' })
    await expect(pending).resolves.toEqual({ id: 'a1' })
  })

  it('shows the sentence the server sent as an error', async () => {
    const pending = upload()
    answer(400, { error: 'This file is too short.' })
    await expect(pending).rejects.toThrow('This file is too short.')
  })

  it('shows the sentence the server sent as a detail, as it does for a file that is too big', async () => {
    const pending = upload()
    answer(413, { detail: "This file is bigger than 8 GB, which is sukoon's limit." })
    await expect(pending).rejects.toThrow("This file is bigger than 8 GB, which is sukoon's limit.")
  })

  it('falls back to a plain sentence when the body holds no sentence', async () => {
    for (const body of [null, {}, { detail: [{ loc: ['body', 'file'], msg: 'field required' }] }]) {
      const pending = upload()
      answer(422, body)
      await expect(pending).rejects.toThrow('The upload failed.')
    }
  })

  it('says the upload was interrupted when the connection drops', async () => {
    const pending = upload()
    FakeXhr.last.onerror?.()
    await expect(pending).rejects.toThrow('The upload was interrupted.')
  })
})

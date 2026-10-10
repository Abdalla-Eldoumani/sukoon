import { errorSentence } from './client'
import type { Job } from './types'

export class UploadError extends Error {}

/** XMLHttpRequest rather than fetch, because only it reports upload progress in every browser. */
export function uploadFile(
  file: File,
  onProgress: (fraction: number) => void,
  params: Record<string, string> = {},
): Promise<Job> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const query = new URLSearchParams(params).toString()
    xhr.open('POST', `/api/jobs${query ? `?${query}` : ''}`)
    xhr.responseType = 'json'
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total)
    }
    xhr.onload = () => {
      if (xhr.status === 201) resolve(xhr.response as Job)
      else reject(new UploadError(errorSentence(xhr.response) ?? 'The upload failed.'))
    }
    xhr.onerror = () => reject(new UploadError('The upload was interrupted. Check that sukoon is still running.'))
    const form = new FormData()
    form.append('file', file, file.name)
    xhr.send(form)
  })
}

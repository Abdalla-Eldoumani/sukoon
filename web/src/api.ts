export interface Health {
  status: string
  version: string
  device: string
  ffmpeg: { ok: boolean; install: string }
}

export interface Settings {
  preset: 'best' | 'fast'
  device: 'auto' | 'cpu'
  audio_format: string | null
  video_format: string | null
  /** Formats this ffmpeg cannot write, with the encoder each one needs. */
  missing: Record<string, string>
  folder: string
}

/** A fetch that turns the server's error body into an Error with its sentence. */
export async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const text = await response.text()
    let message = text
    try {
      const body = JSON.parse(text) as { detail?: string; error?: string }
      message = body.detail ?? body.error ?? text
    } catch {
      // Not JSON: the text itself is the message.
    }
    throw new Error(message || `The request failed (${response.status}).`)
  }
  return response
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await request(path, init)).json()) as T
}

export function postJson<T>(path: string, body: unknown = {}): Promise<T> {
  return getJson<T>(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function putJson<T>(path: string, body: unknown): Promise<T> {
  return getJson<T>(path, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
}

import type { Action, Payload, Update } from './types';

// Queue calls so a numeric input's blur is committed before Apply/Open/Bios runs.
let queue: Promise<unknown> = Promise.resolve();

export class DesktopError extends Error {
  constructor(message: string, public readonly update?: Update) {
    super(message);
  }
}

export function request(action: Action, payload: Payload = {}): Promise<Update> {
  const pending = queue.then(async () => {
    if (!window.pywebview?.api) throw new Error('Desktop bridge is unavailable');
    const result = await window.pywebview.api.request(action, payload);
    if (!result.ok) throw new DesktopError(result.error || 'Request failed', result.data);
    return result.data || {};
  });
  queue = pending.catch(() => undefined);
  return pending;
}

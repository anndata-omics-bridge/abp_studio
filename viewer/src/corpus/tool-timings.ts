import type { ToolTimings } from './types.js'

/** Validate tool-owned timing documents at the JSON boundary. */
export function validatedToolTimings (document: unknown): ToolTimings {
  const header = document && typeof document === 'object' ? document as Record<string, unknown> : {}
  if (header.format !== 'apb-tool-timings' || header.format_version !== 1) {
    throw new Error('Unsupported tool timing format or version')
  }
  if (typeof header.tool !== 'string' || !header.tool ||
      typeof header.operation !== 'string' || !header.operation ||
      !Array.isArray(header.phases)) {
    throw new Error('Invalid tool timing header')
  }
  const names = new Set<string>()
  const phases: ToolTimings['phases'] = []
  for (const value of header.phases as unknown[]) {
    const phase = value && typeof value === 'object' ? value as Record<string, unknown> : {}
    if (typeof phase.name !== 'string' || !phase.name || names.has(phase.name) ||
        typeof phase.seconds !== 'number' || !Number.isFinite(phase.seconds) || phase.seconds < 0) {
      throw new Error('Invalid tool timing phase')
    }
    names.add(phase.name)
    phases.push({ name: phase.name, seconds: phase.seconds })
  }
  return { format: 'apb-tool-timings', format_version: 1, tool: header.tool, operation: header.operation, phases }
}

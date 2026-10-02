// Versioned, tool-owned timing artifact. Studio reads it without copying values
// into its own StepResult runtime and memory telemetry.

export function validatedToolTimings (document) {
  if (document?.format !== 'apb-tool-timings' || document.format_version !== 1) {
    throw new Error('Unsupported tool timing format or version')
  }
  if (typeof document.tool !== 'string' || !document.tool ||
      typeof document.operation !== 'string' || !document.operation ||
      !Array.isArray(document.phases)) {
    throw new Error('Invalid tool timing header')
  }
  const names = new Set()
  for (const phase of document.phases) {
    if (typeof phase?.name !== 'string' || !phase.name || names.has(phase.name) ||
        typeof phase.seconds !== 'number' || !Number.isFinite(phase.seconds) ||
        phase.seconds < 0) {
      throw new Error('Invalid tool timing phase')
    }
    names.add(phase.name)
  }
  return document
}

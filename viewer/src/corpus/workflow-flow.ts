import type { Artifact, StepReport } from './types.js'

export interface FlowArtifact {
  artifact: Artifact
  producer: number | null
  consumers: number[]
  size: number | null
}

export interface FlowStep {
  report: StepReport
  inputs: FlowArtifact[]
  outputs: FlowArtifact[]
}

/** Match exact recorded paths to the most recent preceding producer. */
export function workflowFlow (steps: StepReport[]): FlowStep[] {
  const producers = new Map<string, { index: number; output: FlowArtifact }>()
  return steps.map((report, index) => {
    const inputs = (report.inputs ?? []).map(artifact => {
      const source = artifact.path ? producers.get(artifact.path) : undefined
      if (source && !source.output.consumers.includes(index)) source.output.consumers.push(index)
      return {
        artifact,
        producer: source?.index ?? null,
        consumers: [],
        size: artifact.size_bytes ?? source?.output.size ?? null
      }
    })
    const outputs = (report.outputs ?? []).map(artifact => {
      const output: FlowArtifact = { artifact, producer: index, consumers: [], size: artifact.size_bytes ?? null }
      if (artifact.path) producers.set(artifact.path, { index, output })
      return output
    })
    return { report, inputs, outputs }
  })
}

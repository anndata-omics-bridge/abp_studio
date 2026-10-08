import assert from 'node:assert/strict'
import { test } from 'node:test'
import { apbMetadataScopes, fastaChecks, structureViews } from '../../viewer/src/corpus/representation.ts'

const provenance = {
  fasta: { provenance: { peptide_verification: { protein_count: 100, sources: { 0: { path: 'ref.fasta' } } } } },
  proteobench: { provenance: { annotation: { source: 'module.toml' } } }
}
const ion = {
  name: 'ion', dimensions: { observations: 6, variables: 50 },
  obs: { row_count: 6, key_columns: ['raw_file'], columns: [{ name: 'raw_file', dtype: 'String' }] },
  var: { row_count: 50, key_columns: ['ion'], columns: [] },
  layers: [{ name: 'Intensity', storage_slot: 'X', primary: true }],
  apb: {
    fasta: { peptide_verification: { matched_feature_count: 49, unmatched_feature_count: 1 } },
    proteobench: { annotation: { matched_observation_count: 6 } }
  }
}
const protein = {
  name: 'protein', dimensions: { observations: 3, variables: 10 },
  apb: { aggregate: { method: 'sum' } }
}
const annotation = {
  name: 'fasta proteins', row_count: 100, key_columns: ['id'],
  columns: [{ name: 'id', dtype: 'String', null_count: 0 }], metadata: { source: 'ref.fasta' }
}
const relation = {
  name: 'peptide_protein', annotation_table: annotation.name, target_level: 'ion',
  coordinates: { row_count: 72 }, metadata: { matching: 'sequence' }
}

test('H5AD keeps result-wide provenance and level results in its single AnnData', () => {
  const combined = { ...ion, apb: {
    fasta: { ...provenance.fasta, ...ion.apb.fasta },
    proteobench: { ...provenance.proteobench, ...ion.apb.proteobench }
  } }
  const representation = { artifact: { physical_format: 'h5ad' }, root: null, levels: [combined] }
  const [view, ...rest] = structureViews(representation)
  assert.equal(rest.length, 0)
  assert.equal(view.kind, 'anndata')
  assert.equal(view.objectPath, 'adata')
  assert.equal(view.diagram.uns, combined.apb, 'display the emitted tree without recomposing it')
  assert.equal(view.diagram.uns.fasta.provenance.peptide_verification.protein_count, 100)
  assert.equal(view.diagram.uns.fasta.peptide_verification.matched_feature_count, 49)
  assert.deepEqual(apbMetadataScopes(representation)[0].value.uns.apb, combined.apb)
  assert.equal(view.hasStorage, true)
  assert.equal('storage' in view.diagram.uns, false, 'do not fabricate a descriptor value')
})

test('H5MU separates root provenance and relations from every embedded AnnData', () => {
  const representation = {
    artifact: { physical_format: 'h5mu' }, root: { apb: {
      ...provenance,
      hierarchy: { name: 'lfq', identities: [['ion', 'ion'], ['protein', 'protein']] },
      annotation_tables: { 'fasta proteins': { key_columns: ['id'], metadata: annotation.metadata } },
      feature_relations: { peptide_protein: { annotation_table: annotation.name, target_level: 'ion', metadata: relation.metadata } }
    } }, levels: [protein, ion],
    annotation_tables: [annotation], feature_relations: [relation]
  }
  const [root, ions, proteins, annotations] = structureViews(representation)
  assert.equal(root.label, 'MuData container')
  assert.deepEqual(root.modalities.map(item => item.name), ['ion', 'protein', 'annotation/fasta proteins'])
  assert.deepEqual(root.relations, [relation])
  assert.equal(root.uns, representation.root.apb)
  assert.deepEqual(root.uns.annotation_tables, {
    'fasta proteins': { key_columns: ['id'], metadata: annotation.metadata }
  })
  assert.deepEqual(root.uns.feature_relations, {
    peptide_protein: { annotation_table: annotation.name, target_level: 'ion', metadata: relation.metadata }
  })
  assert.deepEqual(apbMetadataScopes(representation)[0].value.uns.apb, root.uns)
  assert.equal(ions.objectPath, 'mdata.mod["ion"]')
  assert.deepEqual(ions.diagram.uns, ion.apb)
  assert.deepEqual(proteins.diagram.uns, protein.apb)
  assert.equal('provenance' in ions.diagram.uns.fasta, false)
  assert.equal(proteins.diagram.dimensions.observations, 3)
  assert.deepEqual(annotations.diagram.dimensions, { observations: 6, variables: 100 })
  assert.equal(annotations.diagram.x, null)
  assert.deepEqual(annotations.diagram.layers, [])
  assert.deepEqual(annotations.diagram.uns, {})
  assert.equal(annotations.hasStorage, false)
  assert.equal(annotations.diagram.obs, ion.obs)
  assert.equal(annotations.diagram.var, annotation)
  assert.deepEqual(representation.levels, [protein, ion], 'projection must not reorder the sidecar')
  assert.equal('annotation_tables' in provenance, false, 'projection must not mutate the sidecar')
})


test('custom hierarchy determines embedded AnnData order', () => {
  const representation = {
    artifact: { physical_format: 'h5mu' },
    root: { apb: { hierarchy: { name: 'enrichment', identities: [['peptidoform', 'form'], ['multisite', 'multisite'], ['site', 'site']] } } },
    levels: [{ name: 'site' }, { name: 'peptidoform' }, { name: 'multisite' }]
  }
  const [root] = structureViews(representation)
  assert.deepEqual(root.modalities.map(item => item.name), ['peptidoform', 'multisite', 'site'])
})

test('FASTA check counts and source stay paired in standalone AnnData', () => {
  const representation = { root: null, levels: [{ ...ion, apb: {
    fasta: { ...provenance.fasta, ...ion.apb.fasta }
  } }] }
  assert.deepEqual(fastaChecks(representation), [{
    level: 'ion', matched_feature_count: 49, unmatched_feature_count: 1,
    protein_count: 100, sources: { 0: { path: 'ref.fasta' } }
  }])
})

test('FASTA checks use MuData source provenance without assigning checks to unchecked levels', () => {
  const representation = {
    root: { apb: { fasta: { provenance: { peptide_verification: {
      sources: { 0: { path: 'HYE.fasta', checksum: 'reference-checksum' } }, il_equivalent: false
    } } } } },
    levels: [ion, protein, { ...ion, name: 'peptide', apb: { fasta: {
      peptide_verification: { matched_feature_count: 0, unmatched_feature_count: 2 },
      provenance: { peptide_verification: { sources: { 0: { path: 'other.fasta' } }, il_equivalent: true } }
    } } }]
  }
  const snapshot = structuredClone(representation)
  assert.deepEqual(fastaChecks(representation), [
    { level: 'ion', matched_feature_count: 49, unmatched_feature_count: 1,
      sources: { 0: { path: 'HYE.fasta', checksum: 'reference-checksum' } }, il_equivalent: false },
    { level: 'peptide', matched_feature_count: 0, unmatched_feature_count: 2,
      sources: { 0: { path: 'other.fasta' } }, il_equivalent: true }
  ])
  assert.deepEqual(representation, snapshot)
})

test('missing FASTA provenance stays unknown and conversion alone has no FASTA checks', () => {
  assert.deepEqual(fastaChecks({ levels: [ion] }), [
    { level: 'ion', matched_feature_count: 49, unmatched_feature_count: 1 }
  ])
  assert.deepEqual(fastaChecks({ levels: [protein] }), [])
  assert.deepEqual(fastaChecks({ root: { apb: provenance }, levels: [protein] }), [])
})

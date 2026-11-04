import type { Field, Row, RuleDocument, Table, Value } from '../types.js'
import { cellText, tableOf } from './tables.js'

// The Rules tab: one row per packaged rules.json, its input policy table by table.

export const RULE_FIELDS: Field[] = [
  { name: 'software', description: 'The quantification tool whose output the rule reads.' },
  { name: 'versions', description: 'software_version_pattern: the regular expression a version from the parameter file must match for this rule to apply.' },
  { name: 'rule', description: 'The rules.json, as its path below apb2\'s packaged rule documents.' },
  { name: 'acquisition', description: 'The acquisition methods apb2\'s rule catalog lists the rule under.' },
  { name: 'levels', description: 'The levels the rule declares, one feature type each; click the row to see them.' },
  { name: 'shape', description: 'long: one row per sample and feature; wide: one row per feature, one column per sample and quantity.' },
  { name: 'extensions', description: 'The file extensions the rule reads.' },
  { name: 'preparation', description: 'A preparation step, a short Python function that joins several tables or files into the table the rule describes.' },
  { name: 'detection', description: 'How apb2 recognizes the tool without a parameter file: columns a report must have or lack, and the acquisition method it then assumes.' },
  { name: 'parameter_file', description: 'required: conversion needs the tool\'s parameter file; none: the tool writes none.' },
  { name: 'file_version', description: 'The rule\'s own version, raised when its declarations change.' }
]

/** Distinct texts of `values`, in first-seen order, joined by ` | `. */
export function distinct (values: Value[]): string {
  return [...new Set(values.map(cellText).filter(text => text !== ''))].join(' | ')
}

/** One row per document; a document with several tables joins their values. */
export function ruleRows (rules: RuleDocument[]): Table {
  const rows: Row[] = rules.map(rule => ({
    software: rule.software_name,
    versions: rule.software_version_pattern,
    rule: rule.rule,
    acquisition: rule.categories,
    levels: rule.levels,
    shape: distinct(rule.tables.map(table => table.input.shape ?? null)),
    extensions: distinct(rule.tables.map(table => table.input.extensions ?? null)),
    preparation: distinct(rule.tables.map(table => table.preparation)),
    detection: distinct(rule.tables.map(table => table.input.without_parameter_file ?? null)),
    parameter_file: rule.parameter_file,
    file_version: rule.file_version
  }))
  return tableOf(rows, RULE_FIELDS.map(field => field.name))
}

/** How the rule picker names a rule: software, version pattern and path. */
export function ruleLabel (rule: RuleDocument): string {
  return `${rule.software_name} ${rule.software_version_pattern} · ${rule.rule}`
}

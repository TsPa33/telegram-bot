// Readiness v8 is independent of the existing Workshop v7 gate.
export const SMART_REVISION = 'a73e05b9c842';
export const SMART_FEATURES = ['tenant_ranked_parts','direction_constraints','dictionary_aliases','bounded_typo_search'] as const;
export function isSmartReady(value: unknown): boolean {
 if (!value || typeof value !== 'object') return false;
 const r = value as Record<string, unknown>;
 return r.status === 'ready' && r.contract_version === 8 && r.required_revision === SMART_REVISION
  && Array.isArray(r.database_revisions) && r.database_revisions.length === 1
  && r.database_revisions[0] === SMART_REVISION && Array.isArray(r.features)
  && SMART_FEATURES.every(f => (r.features as unknown[]).includes(f));
}

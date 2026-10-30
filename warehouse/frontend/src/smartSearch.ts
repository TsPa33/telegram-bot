// Readiness v8 is independent of the existing Workshop v7 gate.
export const SMART_REVISION = 'a73e05b9c842';
export const SMART_FEATURES = ['tenant_ranked_parts','direction_constraints','dictionary_aliases','bounded_typo_search'] as const;
export function isSmartReady(value: unknown): boolean {
 if (!value || typeof value !== 'object') return false;
 const r = value as Record<string, unknown>;
 return r.status === 'ready' && r.contract_version === 8 && r.required_revision === SMART_REVISION
  && Array.isArray(r.database_revisions) && r.database_revisions.length === 1
  && [SMART_REVISION,'b94f62d18e07','b8716962f6b8','021e8f6f220c','41f9a2c87d10','5c7d9e1a320f','76af12de4b90','84d2c6fa190b','95c3e7b12a04','a6d94c72e310','b7e14d90c2f6','c8f21d6e903a'].includes(r.database_revisions[0]) && Array.isArray(r.features)
  && SMART_FEATURES.every(f => (r.features as unknown[]).includes(f));
}

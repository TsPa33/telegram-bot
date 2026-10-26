export const TEAM_REVISION='b94f62d18e07';
export const TEAM_FEATURES=['workspace_actor_separation','server_permissions','live_session_revocation','financial_redaction','actor_bound_replay'];
export function isTeamReady(value:unknown):boolean {
 if(!value||typeof value!=='object')return false;
 const r=value as Record<string,unknown>;
 return r.status==='ready'&&r.contract_version===9&&r.required_revision===TEAM_REVISION
  &&Array.isArray(r.database_revisions)&&r.database_revisions.length===1&&r.database_revisions[0]===TEAM_REVISION
  &&Array.isArray(r.features)&&TEAM_FEATURES.every(f=>(r.features as unknown[]).includes(f))
  &&typeof r.employee_creation_enabled==='boolean';
}

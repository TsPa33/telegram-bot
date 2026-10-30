export const TEAM_REVISION='b94f62d18e07';
export const TEAM_FEATURES=['workspace_actor_separation','server_permissions','live_session_revocation','financial_redaction','actor_bound_replay'];
export function isTeamReady(value:unknown):boolean {
 if(!value||typeof value!=='object')return false;
 const r=value as Record<string,unknown>;
 return r.status==='ready'&&r.contract_version===9&&r.required_revision===TEAM_REVISION
  &&Array.isArray(r.database_revisions)&&r.database_revisions.length===1&&[TEAM_REVISION,'b8716962f6b8','021e8f6f220c','41f9a2c87d10','5c7d9e1a320f','76af12de4b90','84d2c6fa190b','95c3e7b12a04','a6d94c72e310','b7e14d90c2f6','c8f21d6e903a'].includes(r.database_revisions[0] as string)
  &&Array.isArray(r.features)&&TEAM_FEATURES.every(f=>(r.features as unknown[]).includes(f))
  &&typeof r.employee_creation_enabled==='boolean';
}

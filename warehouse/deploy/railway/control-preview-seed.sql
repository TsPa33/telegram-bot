-- Isolated synthetic preview only; no production or Warehouse source data.
\getenv owner_hash PREVIEW_OWNER_HASH
\getenv owner_cipher PREVIEW_OWNER_CIPHER
INSERT INTO control_center.staff(id,username,password_hash,mfa_ciphertext,last_totp_step,role,finance,active,created_at)
VALUES ('00000000-0000-4000-8000-000000000001','preview-owner',:'owner_hash',:'owner_cipher',-1,'Owner',false,true,now()),
('00000000-0000-4000-8000-000000000002','demo-manager','demo-no-login','demo-no-login',-1,'Manager',false,true,now()),
('00000000-0000-4000-8000-000000000003','demo-support','demo-no-login','demo-no-login',-1,'Support',false,true,now());
WITH demo(id,name,plan,status,vehicles,capacity,employees,seats,days,registered) AS (
 VALUES (1,'ДЕМО · AutoParts Київ','standard','ACTIVE',8,10,3,5,12,32),
 (2,'ДЕМО · Volvo Garage','premium','ACTIVE',32,50,6,10,26,60),
 (3,'ДЕМО · Auto West','free','FREE',0,0,0,0,0,2),
 (4,'ДЕМО · Motor Service','standard','EXPIRED',4,10,1,5,-2,40),
 (5,'ДЕМО · Parts Hub','standard','TRIAL',2,10,1,5,7,3)
)
INSERT INTO control_center.companies(id,environment,workspace_id,display_name,search_text,labels,snapshot,registered_at,fetched_at)
SELECT '10000000-0000-4000-8000-'||lpad(id::text,12,'0'),'staging','20000000-0000-4000-8000-'||lpad(id::text,12,'0'),name,lower(name||' owner'||id||'@example.test'),'["Демонстрація"]'::json,
json_build_object('source_environment','staging','access',json_build_object('status',status,'plan',plan,'vehicle_capacity',capacity,'employee_seats',seats,'period_end',now()+make_interval(days=>days),'continuous_paid_until',CASE WHEN status='ACTIVE' THEN now()+make_interval(days=>days) ELSE NULL END),'usage',json_build_object('vehicles',vehicles,'employees',employees),'access_incomplete',false,'binding',NULL,'people',json_build_array(json_build_object('id','demo-'||id,'name','Демо власник '||id,'email','owner'||id||'@example.test','role','DIRECTOR','active',true,'last_login_at',now()-interval '1 day')),'business_activity_at',now()-interval '2 days','business_activity_coverage','synthetic preview'), now()-make_interval(days=>registered),now()
FROM demo;
INSERT INTO control_center.source_links(id,company_id,system,environment,entity_type,source_id,status,evidence,verified_by,verified_at)
SELECT gen_random_uuid()::text,id,'warehouse','staging','workspace',workspace_id,'verified','synthetic-preview','preview-seed',now() FROM control_center.companies;
INSERT INTO control_center.source_state(key,environment,schema_version,last_success,fetched_at,coverage) VALUES ('warehouse:staging','staging','001',now(),now(),'sweep_complete');
INSERT INTO control_center.tasks(id,company_id,assignee_id,next_action,status,due_at,created_at)
SELECT gen_random_uuid()::text,id,'00000000-0000-4000-8000-000000000001','Допомогти обрати тариф','open',now()+interval '1 day',now() FROM control_center.companies WHERE display_name LIKE '%Auto West%';

export function referralCode(value:string|null|undefined){const code=(value||'').trim().toUpperCase();return /^[A-F0-9]{16}$/.test(code)?code:null;}
export function referralInvite(search:string){const p=new URLSearchParams(search);return p.get('section')==='referrals'?referralCode(p.get('ref')):null;}
export function referralPath(code:string){const value=referralCode(code);if(!value)throw Error('Некоректний код запрошення');return '/settings?section=referrals&ref='+value;}

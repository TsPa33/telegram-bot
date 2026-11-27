// Staging can pause automated price references without changing manual selling prices.
export const marketReferenceEnabled = (import.meta as ImportMeta & {env?: Record<string,string|undefined>}).env?.VITE_WAREHOUSE_MARKET_REFERENCE_ENABLED !== 'false';

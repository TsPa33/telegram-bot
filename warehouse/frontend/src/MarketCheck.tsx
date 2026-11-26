import type {Row} from './api';
import AletoPriceButton from './AletoPriceButton';

export default function MarketCheck({part,vehicle}:{part:Row;vehicle?:Row|null}){
 return <section className="r5-market" aria-label="Перевірка ринкових даних"><AletoPriceButton part={part} vehicle={vehicle}/></section>;
}

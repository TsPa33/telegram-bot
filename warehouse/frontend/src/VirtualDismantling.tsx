import type { Row } from "./api";
import PlanPartsDonorAnalysis from "./PlanPartsDonorAnalysis";

/**
 * Vehicle dismantling has one supported user-facing workflow: Plan.Parts.
 * The experimental CarPot base checklist is retained server-side for historical
 * compatibility, but is not an option on the warehouse vehicle page.
 */
export default function VirtualDismantling({
  vehicle,
  onSaved,
}: {
  vehicle: Row;
  onSaved: (row: Row) => void;
}) {
  return (
    <PlanPartsDonorAnalysis
      key={String(vehicle.id)}
      vehicle={vehicle}
      onSaved={onSaved}
    />
  );
}

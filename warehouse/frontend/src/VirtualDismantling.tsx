import type { Row } from "./api";
import UnifiedCatalogue from "./UnifiedCatalogue";

/** Reuses the existing dismantling board and explicit paid Plan.Parts flow. */
export default function VirtualDismantling({
  vehicle,
  onSaved,
  onModify,
  view = "operations",
}: {
  vehicle: Row;
  onSaved: (row: Row) => void;
  onModify?: () => void;
  view?: "operations" | "settings";
}) {
  return (
    <UnifiedCatalogue
      key={String(vehicle.id)}
      vehicle={vehicle}
      onSaved={onSaved}
      onModify={onModify}
      view={view}
    />
  );
}
